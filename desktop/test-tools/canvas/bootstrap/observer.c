/* Test-only preload. Replaces the first public Mistral document, observes native
 * signals, and never calls policy use/ignore or replaces an opener/policy handler.
 * Compile into the evidence directory; this library is never part of the app. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <webkit2/webkit2.h>

static gboolean injected, hooks_installed;
static guint sequence, next_view;
static void attach(WebKitWebView *view);

static gboolean enabled(void) {
    return g_strcmp0(g_getenv("VIBEZ_CANVAS_MODE"), "controlled-html") == 0;
}
static char *origin_only(const char *uri) {
    if (!uri) return g_strdup("none");
    if (!strcmp(uri, "about:blank")) return g_strdup("about:blank");
    GUri *url = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
    if (!url) return g_strdup("unparseable");
    const char *scheme = g_uri_get_scheme(url), *host = g_uri_get_host(url);
    char *value;
    if (scheme && host && (!strcmp(scheme,"http") || !strcmp(scheme,"https"))) {
        int port = g_uri_get_port(url);
        value = port > 0 ? g_strdup_printf("%s://%s:%d",scheme,host,port)
                         : g_strdup_printf("%s://%s",scheme,host);
    } else value = g_strdup("non-http-origin");
    g_uri_unref(url);
    return value;
}
static const char *fixture_case(const char *uri) {
    if (!uri) return NULL;
    GUri *url = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
    if (!url) return NULL;
    const char *path=g_uri_get_path(url), *query=g_uri_get_query(url), *tag=NULL;
    if (path && query && (!strcmp(path,"/cdn-cgi/preview-platform/vibez-synthetic-routing-probe") || !strcmp(path,"/cdn-cgi/challenge-platform/vibez-synthetic-routing-probe") ||
                         !strcmp(path,"/vibez-synthetic-routing-probe"))) {
        static const char *cases[]={"unnamed","named","unnamed-retry","preview-popup","external-normal"};
        for (guint i=0;i<G_N_ELEMENTS(cases);i++) {
            char *expected=g_strdup_printf("vibez_case=%s",cases[i]);
            if (!strcmp(query,expected)) tag=cases[i];
            g_free(expected);
        }
    }
    g_uri_unref(url);
    return tag;
}
static char *uri_fields(const char *uri) {
    char *origin=origin_only(uri);
    const char *tag=fixture_case(uri);
    char *fields=g_strdup_printf("\"origin\":\"%s\",\"fixtureCase\":%s%s%s",origin,
        tag?"\"":"",tag?tag:"null",tag?"\"":"");
    g_free(origin); return fields;
}
static void row(WebKitWebView *view, const char *event, const char *details) {
    const char *path=g_getenv("VIBEZ_CANVAS_NATIVE_LOG");
    if (!path || path[0]!='/') return;
    FILE *file=fopen(path,"a");
    if (!file) return;
    guint id=view?GPOINTER_TO_UINT(g_object_get_data(G_OBJECT(view),"vibez-canvas-view")):0;
    fprintf(file,"{\"sequence\":%u,\"pid\":%ld,\"monotonicUs\":%lld,\"view\":%u,\"event\":\"%s\"%s%s}\n",
        ++sequence,(long)getpid(),(long long)g_get_monotonic_time(),id,event,details?",":"",details?details:"");
    fclose(file);
}
static gboolean public_mistral(const char *uri) {
    GUri *url=uri?g_uri_parse(uri,G_URI_FLAGS_NONE,NULL):NULL;
    if (!url) return FALSE;
    const char *host=g_uri_get_host(url); int port=g_uri_get_port(url);
    gboolean result=g_strcmp0(g_uri_get_scheme(url),"https")==0 && (port==-1 || port==443) &&
        !g_uri_get_userinfo(url) && (g_strcmp0(host,"vibe.mistral.ai")==0 || g_strcmp0(host,"chat.mistral.ai")==0);
    g_uri_unref(url); return result;
}
static char *action_fields(WebKitNavigationAction *action) {
    WebKitURIRequest *request=webkit_navigation_action_get_request(action);
    char *fields=uri_fields(request?webkit_uri_request_get_uri(request):NULL);
    const char *frame=webkit_navigation_action_get_frame_name(action);
    const char *named=!frame?"null":!strcmp(frame,"vibez-canvas-named")?"\"our-named-frame\"":"\"other-name-present\"";
    char *result=g_strdup_printf("%s,\"frameName\":%s,\"userGesture\":%s,\"redirect\":%s",fields,named,
        webkit_navigation_action_is_user_gesture(action)?"true":"false",webkit_navigation_action_is_redirect(action)?"true":"false");
    g_free(fields); return result;
}
/* TRUE keeps an emission hook installed; it is NOT the signal handler result.
 * Frame names are diagnostic metadata, never a main-frame classification. */
static gboolean policy_hook(GSignalInvocationHint *hint,guint n,const GValue *values,gpointer data) {
    (void)hint;(void)data;
    if (n<3) return TRUE;
    WebKitWebView *view=g_value_get_object(&values[0]); attach(view);
    WebKitPolicyDecision *decision=g_value_get_object(&values[1]);
    WebKitPolicyDecisionType type=g_value_get_enum(&values[2]);
    char *fields=NULL,*details=NULL;
    if (type==WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION || type==WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION) {
        fields=action_fields(webkit_navigation_policy_decision_get_navigation_action(WEBKIT_NAVIGATION_POLICY_DECISION(decision)));
        details=g_strdup_printf("\"type\":\"%s\",%s",type==WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION?"navigation-action":"new-window-action",fields);
    } else if (type==WEBKIT_POLICY_DECISION_TYPE_RESPONSE) {
        WebKitResponsePolicyDecision *response=WEBKIT_RESPONSE_POLICY_DECISION(decision);
        fields=uri_fields(webkit_uri_request_get_uri(webkit_response_policy_decision_get_request(response)));
        WebKitURIResponse *http=webkit_response_policy_decision_get_response(response);
        details=g_strdup_printf("\"type\":\"response\",%s,\"mainFrameMainResource\":%s,\"httpStatus\":%u",fields,
            webkit_response_policy_decision_is_main_frame_main_resource(response)?"true":"false",http?webkit_uri_response_get_status_code(http):0);
    }
    row(view,"policy-observed",details);g_free(fields);g_free(details);return TRUE;
}
static gboolean create_hook(GSignalInvocationHint *hint,guint n,const GValue *values,gpointer data) {
    (void)hint;(void)data;
    if (n<2) return TRUE;
    WebKitWebView *view=g_value_get_object(&values[0]);attach(view);
    WebKitNavigationAction *action=g_value_get_boxed(&values[1]);
    if (action) { char *fields=action_fields(action);row(view,"create-request-observed",fields);g_free(fields); }
    return TRUE;
}
static void resource_finished(WebKitWebResource *resource,gpointer data) {
    WebKitWebView *view=data;
    WebKitURIResponse *response=webkit_web_resource_get_response(resource);
    char *fields=uri_fields(webkit_web_resource_get_uri(resource));
    char *details=g_strdup_printf("%s,\"httpStatus\":%u",fields,response?webkit_uri_response_get_status_code(response):0);
    row(view,"resource-finished",details);g_free(fields);g_free(details);
}
static void resource_failed(WebKitWebResource *resource,GError *error,gpointer data) {
    WebKitWebView *view=data;char *fields=uri_fields(webkit_web_resource_get_uri(resource));
    char *details=g_strdup_printf("%s,\"errorCode\":%d",fields,error?error->code:0);
    row(view,"resource-failed",details);g_free(fields);g_free(details);
}
static void resource_started(WebKitWebView *view,WebKitWebResource *resource,WebKitURIRequest *request,gpointer data) {
    (void)data;const char *uri=webkit_uri_request_get_uri(request);
    if (!fixture_case(uri)) return;
    char *fields=uri_fields(uri);row(view,"resource-load-started",fields);g_free(fields);
    g_signal_connect_object(resource,"finished",G_CALLBACK(resource_finished),view,0);
    g_signal_connect_object(resource,"failed",G_CALLBACK(resource_failed),view,0);
}
static void click_own_fixture(WebKitWebView *view) {
    if(g_object_get_data(G_OBJECT(view),"vibez-canvas-clicked"))return;
    g_object_set_data(G_OBJECT(view),"vibez-canvas-clicked",GINT_TO_POINTER(1));
    GtkWidget *widget=GTK_WIDGET(view);GdkWindow *window=gtk_widget_get_window(widget);
    if(!window){row(view,"native-click-unavailable",NULL);return;}
    GdkDisplay *display=gtk_widget_get_display(widget);GdkSeat *seat=gdk_display_get_default_seat(display);
    GdkDevice *pointer=seat?gdk_seat_get_pointer(seat):NULL;
    gint root_x=0,root_y=0;gdk_window_get_origin(window,&root_x,&root_y);
    gboolean consumed[2]={FALSE,FALSE};
    for(guint i=0;i<2;i++){
        GdkEvent *event=gdk_event_new(i?GDK_BUTTON_RELEASE:GDK_BUTTON_PRESS);
        event->button.window=g_object_ref(window);event->button.send_event=TRUE;
        event->button.time=GDK_CURRENT_TIME;event->button.x=164;event->button.y=220;
        event->button.x_root=root_x+164;event->button.y_root=root_y+220;
        event->button.state=i?GDK_BUTTON1_MASK:0;event->button.button=1;
        if(pointer)gdk_event_set_device(event,pointer);
        consumed[i]=gtk_widget_event(widget,event);gdk_event_free(event);
    }
    char *details=g_strdup_printf("\"scopedToOwnWebview\":true,\"pressConsumed\":%s,\"releaseConsumed\":%s",consumed[0]?"true":"false",consumed[1]?"true":"false");
    row(view,"native-click-dispatched",details);g_free(details);
}
static void evaluated(GObject *object,GAsyncResult *result,gpointer data) {
    (void)data;GError *error=NULL;
    JSCValue *value=webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(object),result,&error);
    if (error) { row(WEBKIT_WEB_VIEW(object),"fixture-eval-error",NULL);g_error_free(error);return; }
    char *json=value?jsc_value_to_string(value):NULL;
    if (json && strlen(json)<8192) {
        char *fields=g_strdup_printf("\"ownFixtureState\":%s",json);row(WEBKIT_WEB_VIEW(object),"fixture-state",fields);g_free(fields);
        if(strstr(json,"\"controlledFixture\":true") && strstr(json,"\"readyForPopup\":true") && strstr(json,"\"popupAttempted\":false"))click_own_fixture(WEBKIT_WEB_VIEW(object));
    }
    g_free(json);if(value)g_object_unref(value);
}
static void auxiliary_evaluated(GObject *object,GAsyncResult *result,gpointer data) {
    (void)data;GError *error=NULL;
    JSCValue *value=webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(object),result,&error);
    if(error){g_error_free(error);return;}
    char *json=value?jsc_value_to_string(value):NULL;
    if(json && strlen(json)<2048){char *fields=g_strdup_printf("\"probe\":%s",json);row(WEBKIT_WEB_VIEW(object),"auxiliary-probe",fields);g_free(fields);}
    g_free(json);if(value)g_object_unref(value);
}
static void auxiliary_probe(WebKitWebView *view) {
    const char *uri=webkit_web_view_get_uri(view);if(!uri)return;
    const char *script=NULL;
    if(fixture_case(uri) && !strcmp(fixture_case(uri),"preview-popup")) {
        script="JSON.stringify((()=>{if(!window.__vzIPC){window.__vzIPC='pending';if(window.__TAURI__?.core?.invoke)window.__TAURI__.core.invoke('get_state').then(()=>window.__vzIPC='UNSAFE',()=>window.__vzIPC='denied');else window.__vzIPC='denied';}return {kind:'canvas-popup',origin:location.origin,openerPresent:!!window.opener,nativeIPC:window.__vzIPC}})())";
    } else if(g_str_has_prefix(uri,"tauri://localhost/") || g_str_has_prefix(uri,"http://tauri.localhost/")) {
        script="JSON.stringify((()=>{if(!window.__vzAuthProbe && performance.now()>3500){window.__vzAuthProbe='pending';window.__TAURI__?.core?.invoke('get_diagnostics').then(s=>window.__vzAuthProbe=s.includes('Authentication routing mode: inactive')?'inactive':'active-or-unavailable',()=>window.__vzAuthProbe='unavailable');}return {kind:'local-shell',authMode:window.__vzAuthProbe}})())";
    }
    if(script)webkit_web_view_evaluate_javascript(view,script,-1,NULL,"vibez-controlled-auxiliary-probe.js",NULL,auxiliary_evaluated,NULL);
}
static guint collect_views(GtkWidget *widget) {
    if (WEBKIT_IS_WEB_VIEW(widget)) { attach(WEBKIT_WEB_VIEW(widget));auxiliary_probe(WEBKIT_WEB_VIEW(widget));return 1; }
    guint count=0;
    if (GTK_IS_CONTAINER(widget)) {
        GList *children=gtk_container_get_children(GTK_CONTAINER(widget));
        for (GList *it=children;it;it=it->next) count+=collect_views(GTK_WIDGET(it->data));
        g_list_free(children);
    }
    return count;
}
typedef struct {WebKitWebView *view;guint count;} Poll;
static gboolean poll_fixture(gpointer data) {
    Poll *poll=data;
    guint windows=0,views=0;
    GList *tops=gtk_window_list_toplevels();
    for (GList *it=tops;it;it=it->next) {
        guint count=collect_views(GTK_WIDGET(it->data));
        if(count){windows++;views+=count;}
    }
    g_list_free(tops);
    char *fields=g_strdup_printf("\"ownWebviewWindows\":%u,\"ownWebviews\":%u",windows,views);
    row(poll->view,"own-window-count",fields);g_free(fields);
    if (public_mistral(webkit_web_view_get_uri(poll->view))) {
        static const char script[]="JSON.stringify((()=>{const s=window.__vibezCanvas;return s&&s.controlledFixture===true?{...s,origin:location.origin,readyState:document.readyState}:{controlledFixture:false}})())";
        webkit_web_view_evaluate_javascript(poll->view,script,-1,NULL,"vibez-canvas-controlled-probe.js",NULL,evaluated,NULL);
    }
    return ++poll->count<80?G_SOURCE_CONTINUE:G_SOURCE_REMOVE;
}
static void free_poll(gpointer data) {Poll *poll=data;g_object_unref(poll->view);g_free(poll);}
static void load_changed(WebKitWebView *view,WebKitLoadEvent event,gpointer data) {
    (void)data;char *fields=uri_fields(webkit_web_view_get_uri(view));
    char *details=g_strdup_printf("\"loadEvent\":%d,%s",event,fields);row(view,"load-changed",details);g_free(fields);g_free(details);
}
static void attach(WebKitWebView *view) {
    if(g_object_get_data(G_OBJECT(view),"vibez-canvas-view"))return;
    g_object_set_data(G_OBJECT(view),"vibez-canvas-view",GUINT_TO_POINTER(++next_view));
    g_signal_connect_after(view,"load-changed",G_CALLBACK(load_changed),NULL);
    g_signal_connect_after(view,"resource-load-started",G_CALLBACK(resource_started),NULL);
    row(view,"webview-observed",NULL);
}
static void install_hooks(WebKitWebView *view) {
    if(hooks_installed)return;
    hooks_installed=TRUE;
    const char *names[]={"decide-policy","create"};
    GSignalEmissionHook callbacks[]={policy_hook,create_hook};
    for(guint i=0;i<G_N_ELEMENTS(names);i++){
        guint id=g_signal_lookup(names[i],G_OBJECT_TYPE(view));GSignalQuery query={0};g_signal_query(id,&query);
        gulong hook=id && !(query.signal_flags&G_SIGNAL_NO_HOOKS)?g_signal_add_emission_hook(id,0,callbacks[i],NULL,NULL):0;
        char *details=g_strdup_printf("\"signal\":\"%s\",\"hookInstalled\":%s",names[i],hook?"true":"false");
        row(view,"observer-installed",details);g_free(details);
    }
}
void webkit_web_view_load_uri(WebKitWebView *view,const gchar *uri) {
    typedef void(*LoadUri)(WebKitWebView*,const gchar*);static LoadUri original;
    if(!original)original=(LoadUri)dlsym(RTLD_NEXT,"webkit_web_view_load_uri");
    if(!original)return;
    if(!enabled()){original(view,uri);return;}
    attach(view);install_hooks(view);
    if(!injected && public_mistral(uri)){
        const char *path=g_getenv("VIBEZ_CANVAS_FIXTURE");gchar *html=NULL;gsize length=0;
        if(path && path[0]=='/' && g_file_get_contents(path,&html,&length,NULL) && length<65536){
            injected=TRUE;
            row(view,"controlled-html-replacement","\"baseOrigin\":\"https://chat.mistral.ai\",\"nativeNavigationHandlersUnchanged\":true");
            Poll *poll=g_new0(Poll,1);poll->view=g_object_ref(view);
            g_timeout_add_full(G_PRIORITY_DEFAULT,250,poll_fixture,poll,free_poll);
            webkit_web_view_load_html(view,html,"https://chat.mistral.ai/");g_free(html);return;
        }
        g_free(html);row(view,"fixture-read-failed",NULL);
    }
    original(view,uri);
}
