//! Linux document routing. A navigation action has no reliable frame identity;
//! WebKit's response decision supplies it before the document can commit.
//! This is a document boundary, not a network firewall: provisional HTTPS
//! requests (including redirects) may already have reached their destination.
use crate::{auth, link_trace, policy, PreviewState};
use tauri::{AppHandle, Manager, Webview};
use tauri_plugin_opener::OpenerExt;
use url::Url;
use webkit2gtk::{
    glib::{prelude::ObjectExt, Cast},
    NavigationPolicyDecision, NavigationPolicyDecisionExt, NavigationType, PolicyDecisionExt,
    PolicyDecisionType, ResponsePolicyDecision, ResponsePolicyDecisionExt, URIRequestExt,
    URIResponseExt, WebViewExt,
};

fn reserved_invalid(url: &Url) -> bool {
    (policy::canvas_preview_target(url) && !policy::embedded_canvas_url(url))
        || (policy::cloudflare_challenge_target(url) && !policy::embedded_challenge_url(url))
}

fn document_url(url: &Url, smoke: bool) -> bool {
    policy::auth_chain_url(url)
        || policy::embedded_internal_url(url)
        || (smoke && policy::local_url(url))
}

fn deliberate_link(gesture: bool, clicked: bool, redirect: bool) -> bool {
    gesture && clicked && !redirect
}

fn authentication_request(app: &AppHandle, request: &webkit2gtk::URIRequest) {
    if let Some(url) = request.uri().and_then(|raw| Url::parse(&raw).ok()) {
        if policy::auth_entry_url(&url) {
            auth::begin(app);
            link_trace::record("auth-mode-start-main-resource", &url);
        }
    }
}

pub fn attach<Allowed, Arrived, Popup>(
    app: &AppHandle,
    view: &Webview,
    allowed: Allowed,
    arrived: Arrived,
    popup_allowed: Popup,
    main: bool,
) -> Result<(), String>
where
    Allowed: Fn(&Url) -> bool + Send + 'static,
    Arrived: Fn(&Url) + Send + 'static,
    Popup: Fn(&Url) -> bool + Send + 'static,
{
    let handle = app.clone();
    let smoke = app.state::<PreviewState>().smoke;
    view.with_webview(move |platform| {
        let native = platform.inner();
        let popup_allowed = std::rc::Rc::new(popup_allowed);
        let creation_allowed = popup_allowed.clone();
        wry::set_webkit_new_window_handler(&native, move |_, action| {
            let Some(url) = action
                .request()
                .and_then(|r| r.uri())
                .and_then(|s| Url::parse(&s).ok())
            else {
                return false;
            };
            if reserved_invalid(&url) {
                return false;
            }
            if creation_allowed(&url) {
                return true;
            }
            let mut action = action.clone();
            if policy::external_url(&url)
                && deliberate_link(
                    action.is_user_gesture(),
                    action.navigation_type() == NavigationType::LinkClicked,
                    action.is_redirect(),
                )
            {
                return true;
            }
            // JavaScript window.open may bypass NewWindowAction completely and
            // can inherit recent user activation even from a delayed timer.
            link_trace::record("automatic-popup-create-block", &url);
            false
        });
        if main {
            let app = handle.clone();
            native.connect_resource_load_started(move |view, resource, request| {
                // Resource identity is native; URL equality/frame names cannot
                // distinguish an auth iframe from a top-level sign-in request.
                if view.main_resource().as_ref() != Some(resource) {
                    return;
                }
                authentication_request(&app, request);
                // The same main resource survives HTTP redirects. Its initial
                // URL can be Chat, with the auth entry appearing only later.
                let redirected_app = app.clone();
                let current_view = view.downgrade();
                // The generated typed binding treats redirected_response as
                // non-null, although it is null for the first sent request.
                resource.connect_local("sent-request", false, move |values| {
                    if let Some(view) = current_view.upgrade() {
                        if let (Ok(resource), Ok(request)) = (
                            values[0].get::<webkit2gtk::WebResource>(),
                            values[1].get::<webkit2gtk::URIRequest>(),
                        ) {
                            if view.main_resource().as_ref() == Some(&resource) {
                                authentication_request(&redirected_app, &request);
                            }
                        }
                    }
                    None
                });
            });
        }
        wry::set_webkit_policy_handler(&native, move |_, decision, kind| {
            match kind {
                PolicyDecisionType::NavigationAction | PolicyDecisionType::NewWindowAction => {
                    let Some(policy) = decision.downcast_ref::<NavigationPolicyDecision>() else {
                        decision.ignore();
                        return true;
                    };
                    let Some(mut action) = policy.navigation_action() else {
                        decision.ignore();
                        return true;
                    };
                    let Some(url) = action
                        .request()
                        .and_then(|r| r.uri())
                        .and_then(|s| Url::parse(&s).ok())
                    else {
                        decision.ignore();
                        return true;
                    };
                    let gesture = action.is_user_gesture();
                    if reserved_invalid(&url) {
                        link_trace::record("navigation-block-invalid-preview", &url);
                        decision.ignore();
                        return true;
                    }
                    if kind == PolicyDecisionType::NewWindowAction {
                        // Related auth/preview popups retain the normal Tauri
                        // creation path. An unsolicited external popup never
                        // invokes the system opener.
                        if popup_allowed(&url)
                            || (policy::external_url(&url)
                                && deliberate_link(
                                    gesture,
                                    action.navigation_type() == NavigationType::LinkClicked,
                                    action.is_redirect(),
                                ))
                        {
                            return false;
                        }
                        link_trace::record("automatic-popup-block", &url);
                        decision.ignore();
                        return true;
                    }
                    // This is a product rule for a deliberate link, including
                    // one clicked inside a frame; it is NOT a frame classifier.
                    if !allowed(&url)
                        && policy::external_url(&url)
                        && deliberate_link(
                            gesture,
                            action.navigation_type() == NavigationType::LinkClicked,
                            action.is_redirect(),
                        )
                    {
                        link_trace::record(
                            if main {
                                "main-open-external"
                            } else {
                                "popup-open-external"
                            },
                            &url,
                        );
                        decision.ignore();
                        if handle
                            .opener()
                            .open_url(url.as_str(), None::<&str>)
                            .is_err()
                        {
                            crate::message(
                                &handle,
                                "Could not open the external link in your browser.",
                            );
                        }
                        return true;
                    }
                    if !document_url(&url, smoke) {
                        link_trace::record("navigation-block-unsafe-document", &url);
                        decision.ignore();
                        return true;
                    }
                    // Preserve Tauri/plugin navigation hooks. The URL-only app
                    // callback on Linux has no side effects; the response gate
                    // below supplies the missing native frame classification.
                    false
                }
                PolicyDecisionType::Response => {
                    let Some(response) = decision.downcast_ref::<ResponsePolicyDecision>() else {
                        decision.ignore();
                        return true;
                    };
                    let Some(url) = response
                        .response()
                        .and_then(|r| r.uri())
                        .and_then(|s| Url::parse(&s).ok())
                    else {
                        decision.ignore();
                        return true;
                    };
                    let top = response.is_main_frame_main_resource();
                    if reserved_invalid(&url)
                        || !document_url(&url, smoke)
                        || (top && !allowed(&url))
                    {
                        link_trace::record(
                            if top {
                                "main-response-block"
                            } else {
                                "frame-response-block"
                            },
                            &url,
                        );
                        decision.ignore();
                        return true;
                    }
                    if top {
                        arrived(&url);
                        link_trace::record("main-response-allow", &url);
                    } else {
                        link_trace::record("frame-response-allow", &url);
                    }
                    // Keep normal MIME/download handling for accepted content.
                    false
                }
                _ => false,
            }
        });
    })
    .map_err(crate::err)
}

pub fn attach_main(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let allowed_app = app.clone();
    let arrived_app = app.clone();
    let popup_app = app.clone();
    let smoke = app.state::<PreviewState>().smoke;
    attach(
        app,
        view,
        move |url| {
            policy::embedded_internal_url(url)
                || (smoke && policy::local_url(url))
                || policy::embedded_canvas_url(url)
                || policy::embedded_challenge_url(url)
                || policy::embedded_url(url)
            || policy::auth_entry_url(url)
                || (auth::active(&allowed_app) && policy::auth_chain_url(url))
        },
        move |url| {
            if policy::auth_return_url(url) {
                auth::end(&arrived_app);
            }
        },
        move |url| auth::main_popup_allowed(&popup_app, url),
        true,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn url(raw: &str) -> Url {
        Url::parse(raw).unwrap()
    }
    #[test]
    fn provisional_documents_exclude_unsafe_origins_and_internal_schemes() {
        assert!(document_url(&url("https://new-preview.example/"), false));
        assert!(document_url(&url("about:srcdoc"), false));
        for raw in [
            "http://example.org/",
            "https://example.org:444/",
            "https://user:secret@example.org/",
            "file:///etc/passwd",
            "data:text/html,hello",
            "javascript:alert(1)",
            "tauri://localhost/",
            "about:blank?x",
        ] {
            assert!(!document_url(&url(raw), false), "{raw}");
        }
    }
    #[test]
    fn invalid_reserved_hosts_never_fall_through_to_external_opener() {
        for raw in [
            "http://canvas.mistralusercontent.com/",
            "https://user@canvas.mistralusercontent.com/",
            "https://canvas.mistralusercontent.com:444/",
            "http://challenges.cloudflare.com/cdn-cgi/challenge-platform/test",
        ] {
            assert!(reserved_invalid(&url(raw)), "{raw}");
        }
    }
    #[test]
    fn new_embedded_origins_do_not_receive_native_controls() {
        for raw in [
            "https://new-preview.example/",
            "https://canvas.mistralusercontent.com/",
            "about:srcdoc",
        ] {
            for label in [
                "vibe",
                "auth-popup-1",
                "shell",
                "settings",
                "screenshot",
                "updates",
            ] {
                assert!(!policy::trusted_caller(label, &url(raw)), "{label}: {raw}");
            }
        }
        assert!(!policy::trusted_caller(
            "vibe",
            &url("tauri://localhost/index.html")
        ));
    }
}
