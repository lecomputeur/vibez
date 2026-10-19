import copy
import unittest
import report

def evidence():
    final={'controlledFixture':True,'finished':True,'origin':'https://chat.mistral.ai','popupErrors':[],
           'messages':[{'case':case} for case in report.READY],'autoPopupReturnedNull':True}
    events=[{'event':'fixture-state','ownFixtureState':final},{'event':'controlled-html-replacement'},
            *({'event':'observer-installed','signal':name,'hookInstalled':True} for name in ('decide-policy','create')),
            *({'event':'own-window-count','ownWebviewWindows':n} for n in (1,2,1))]
    server=[];opens=[]
    def request(case,kind='/content'):server.append({'event':'https-request','case':case,'pathKind':kind,'status':200})
    def response(case,main):events.append({'event':'policy-observed','type':'response','fixtureCase':case,'pathKind':'content','httpStatus':200,'mainFrameMainResource':main})
    for case in report.FRAME_CASES:request(case);response(case,False)
    request('same-url');response('same-url',False)
    for case in report.TOP_CASES:request(case);response(case,True)
    for i,case in enumerate(('redirect-frame','top-redirect','oauth-direct-final','oauth-blank-final')):
        events.append({'event':'resource-sent-request','fixtureCase':case,'resourceId':i+1,'redirectStatus':302})
    for case in report.CLICKS:
        events.append({'event':'policy-observed','fixtureCase':case,'userGesture':True,'navigationType':0})
        opens.append({'case':case,'browserStarted':False})
    for case in ('oauth-direct-final','oauth-blank-final','main-auth-final','login-live-main','login-live-popup-final'):request(case,'/executed')
    request('main-auth-return','/return');request('login-live-return','/return')
    events.extend([{'event':'create-request-observed','fixtureCase':'login-live-popup','navigationType':5,'userGesture':True},{'event':'policy-observed','fixtureCase':'login-live-main','navigationType':0,'userGesture':True}])
    for case in ('main-auth-chain','main-auth-final'):
        events.append({'event':'resource-sent-request','fixtureCase':case,'resourceId':99,'redirectStatus':302})
    return events,server,opens

class StructuralOracleTests(unittest.TestCase):
    def test_related_login_popup_cannot_authorize_main_execution(self):
        states=[{'controlledFixture':True,'trustedClick':True,'popupAliveBeforeMainAttempt':True,'messages':[{'case':'popup-boundary-frame'},{'case':'login-live-boundary-popup-final'}],'finished':True,'currentCase':'complete','origin':'https://chat.mistral.ai'}]
        events=[{'ownFixtureState':states[0]},{'event':'native-click-dispatched','scopedToOwnWebview':True},{'event':'create-request-observed','fixtureCase':'login-live-boundary-popup'},*({'event':'observer-installed','signal':name,'hookInstalled':True} for name in ('decide-policy','create'))]
        for case,main in (('popup-boundary-frame',False),('login-live-boundary-popup-final',True),('top-during-iframe-login-popup',True)):
            events.append({'event':'policy-observed','type':'response','fixtureCase':case,'httpStatus':200,'mainFrameMainResource':main})
        server=[{'event':'https-request','case':'login-live-boundary-popup-final','pathKind':'/executed'}]
        self.assertTrue(report.check_auth_popup_boundary(events,server,[])['ok'])
        server.append({'event':'https-request','case':'top-during-iframe-login-popup','pathKind':'/executed'})
        self.assertFalse(report.check_auth_popup_boundary(events,server,[])['ok'])
        self.assertFalse(report.check_auth_popup_boundary([e for e in events if e.get('fixtureCase')!='login-live-boundary-popup-final'],server[:1],[])['ok'])
    def test_complete_independent_evidence_passes(self):
        self.assertTrue(report.check(*evidence())['ok'])
    def test_navigation_callbacks_cannot_replace_native_response_classification(self):
        e,s,o=evidence();e=[x for x in e if not(x.get('type')=='response' and x.get('fixtureCase')=='unknown-frame')]
        e.append({'event':'policy-observed','type':'navigation-action','fixtureCase':'unknown-frame','frameName':None})
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_same_url_needs_both_main_and_frame_native_flags(self):
        e,s,o=evidence()
        for row in e:
            if row.get('fixtureCase')=='same-url':row['mainFrameMainResource']=False
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_automatic_top_script_or_opener_fails(self):
        e,s,o=evidence();s.append({'event':'https-request','case':'top-auto','pathKind':'/executed'})
        self.assertFalse(report.check(e,s,o)['ok'])
        e,s,o=evidence();o.append({'case':'auto-popup','browserStarted':False})
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_automatic_popup_must_return_null_not_merely_avoid_network(self):
        e,s,o=evidence();e[0]['ownFixtureState']['autoPopupReturnedNull']=False
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_unsafe_resource_start_is_failure_even_without_server_request(self):
        e,s,o=evidence();e.append({'event':'resource-load-started','fixtureCase':'unsafe-port'})
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_click_requires_real_native_gesture_and_link_type(self):
        e,s,o=evidence()
        for row in e:
            if row.get('fixtureCase')=='click-self':row['userGesture']=False
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_auth_iframe_cannot_authorize_main_or_widen_pending(self):
        for case in ('top-after-auth','pending-escape','post-auth-return','post-login-live-return'):
            e,s,o=evidence();s.append({'event':'https-request','case':case,'pathKind':'/executed'})
            self.assertFalse(report.check(e,s,o)['ok'])
    def test_known_login_live_other_popup_and_main_link_cannot_be_dropped(self):
        e,s,o=evidence();e=[row for row in e if row.get('fixtureCase')!='login-live-popup']
        self.assertFalse(report.check(e,s,o)['ok'])
        e,s,o=evidence();s=[row for row in s if row.get('case')!='login-live-main']
        self.assertFalse(report.check(e,s,o)['ok'])
    def test_broken_redirect_resource_identity_fails(self):
        e,s,o=evidence()
        for row in e:
            if row.get('fixtureCase')=='main-auth-final':row['resourceId']=100
        self.assertFalse(report.check(e,s,o)['ok'])

if __name__=='__main__':unittest.main()
