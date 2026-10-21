"""Native structural-routing contract; fixtures and callbacks alone cannot pass."""
def check_auth_popup_boundary(events,server,opens):
    states=[e['ownFixtureState'] for e in events if e.get('ownFixtureState',{}).get('controlledFixture')]
    final=states[-1] if states else {};messages=[m for state in states for m in state.get('messages',[])];checks=[]
    def add(name,passed,evidence=None):checks.append({'name':name,'passed':bool(passed),'evidence':evidence})
    def responses(case,main):return [e for e in events if e.get('event')=='policy-observed' and e.get('type')=='response' and e.get('fixtureCase')==case and e.get('httpStatus')==200 and e.get('mainFrameMainResource') is main]
    def executed(case):return [e for e in server if e.get('event')=='https-request' and e.get('case')==case and e.get('pathKind')=='/executed']
    top='top-during-iframe-login-popup'
    add('Unknown HTTPS iframe rendered and ran its controlled script',bool(responses('popup-boundary-frame',False)) and any(m.get('case')=='popup-boundary-frame' for m in messages))
    add('Popup followed an actual trusted native click',any(state.get('trustedClick') is True for state in states) and any(e.get('event')=='native-click-dispatched' and e.get('scopedToOwnWebview') is True for e in events))
    creates=[e for e in events if e.get('event')=='create-request-observed' and e.get('fixtureCase')=='login-live-boundary-popup']
    add('Iframe requested known login popup through native create',bool(creates),creates)
    add('Related login popup completed its unknown provider redirect',bool(executed('login-live-boundary-popup-final')) and bool(responses('login-live-boundary-popup-final',True)) and any(m.get('case')=='login-live-boundary-popup-final' for m in messages))
    add('Related login popup remained open before the main-navigation attempt',any(state.get('popupAliveBeforeMainAttempt') is True for state in states))
    main_responses=responses(top,True)
    add('Unknown automatic main response was reached but never executed',bool(main_responses) and not executed(top),{'mainResponses':main_responses,'executed':executed(top)})
    add('Main fixture retained its trusted origin and completed',final.get('finished') is True and final.get('currentCase')=='complete' and final.get('origin')=='https://chat.mistral.ai' and not final.get('error'),final)
    add('Neither login popup nor automatic main navigation opened a browser',not opens,opens)
    add('Native observers were installed without replacing app policy handlers',all(any(e.get('event')=='observer-installed' and e.get('signal')==name and e.get('hookInstalled') is True for e in events) for name in ('decide-policy','create')))
    return {'ok':all(c['passed'] for c in checks),'checks':checks,'finalFixtureState':final,'scenario':'auth-popup-boundary','applicationPolicyHandlersChanged':False,'realProviderLoginTested':False}

FRAME_CASES=('unknown-frame','named-frame','nested-parent','nested-child','redirect-frame',
             'known-canvas','known-challenge','auth-iframe','pending-auth-frame','frame-auth-final')
TOP_CASES=('top-after-auth','same-url','top-auto','top-redirect','post-auth-return','post-login-live-return')
UNSAFE=('unsafe-credentials','unsafe-port','unsafe-http','unsafe-file','unsafe-data')
CLICKS=('click-self','click-frame','click-blank','click-http')
READY=('srcdoc-frame',*FRAME_CASES,'same-url','canvas-popup','pending-srcdoc','pending-canvas',
       'oauth-direct-final','oauth-blank-final','oauth-srcdoc','oauth-challenge','login-live-popup-final')

def check(events,server,opens):
    states=[e['ownFixtureState'] for e in events if e.get('ownFixtureState',{}).get('controlledFixture')]
    final=states[-1] if states else {};messages=[m for state in states for m in state.get('messages',[])];checks=[]
    def add(name,ok,evidence=None):checks.append({'name':name,'passed':bool(ok),'evidence':evidence})
    def requests(case):return [e for e in server if e.get('event')=='https-request' and e.get('case')==case and e.get('pathKind')!='/executed']
    def executions(case):return [e for e in server if e.get('event')=='https-request' and e.get('case')==case and e.get('pathKind')=='/executed']
    def responses(case):return [e for e in events if e.get('event')=='policy-observed' and e.get('type')=='response' and e.get('fixtureCase')==case and e.get('pathKind') in ('content','other')]
    def native(case):return [e for e in events if e.get('fixtureCase')==case and e.get('event') in ('policy-observed','create-request-observed')]
    add('Controlled main fixture completed and retained its document',final.get('finished') and not final.get('error') and final.get('origin')=='https://chat.mistral.ai',final.get('error'))
    add('Native observers installed; no application decision handlers replaced',all(any(e.get('event')=='observer-installed' and e.get('signal')==name and e.get('hookInstalled') is True for e in events) for name in ('decide-policy','create')))
    add('Only the initial public document was substituted',sum(e.get('event')=='controlled-html-replacement' for e in events)==1)
    for case in READY:add(case+': actual document script readiness',any(m.get('case')==case for m in messages))
    for case in FRAME_CASES:
        rs=responses(case);add(case+': real HTTPS200 subframe response',bool(requests(case)) and any(e.get('httpStatus')==200 and e.get('mainFrameMainResource') is False for e in rs),rs)
    for case in TOP_CASES:
        rs=responses(case);add(case+': main response classified before denied commit',bool(requests(case)) and any(e.get('httpStatus')==200 and e.get('mainFrameMainResource') is True for e in rs) and not executions(case),{'responses':rs,'executed':len(executions(case))})
    same=responses('same-url');add('Identical URL observed in actual main and subframe responses',any(e.get('mainFrameMainResource') is True for e in same) and any(e.get('mainFrameMainResource') is False for e in same))
    for case in ('redirect-frame','top-redirect','oauth-direct-final','oauth-blank-final'):
        hops=[e for e in events if e.get('event')=='resource-sent-request' and e.get('fixtureCase')==case and e.get('redirectStatus')==302]
        add(case+': actual HTTP redirect chain',bool(hops),hops)
    for case in UNSAFE:
        add(case+': blocked before resource request or script',not requests(case) and not executions(case) and not any(m.get('case')==case for m in messages) and not any(e.get('event')=='resource-load-started' and e.get('fixtureCase')==case for e in events))
    for case in CLICKS:
        clicked=any(e.get('userGesture') is True and e.get('navigationType')==0 for e in native(case))
        add(case+': trusted LinkClicked opens exactly once externally',clicked and sum(e.get('case')==case for e in opens)==1 and not requests(case),native(case))
    add('Automatic top navigation and popup never open a browser',all(e.get('case') in CLICKS for e in opens) and not requests('auto-popup'))
    add('Automatic external popup returns no related window',any(state.get('autoPopupReturnedNull') is True for state in states) and not any(state.get('autoPopupReturnedNull') is False for state in states))
    add('No real browser process was launched',all(e.get('browserStarted') is False for e in opens))
    add('Provider iframe did not authorize automatic main navigation',not executions('top-after-auth'))
    add('Pending auth iframe did not widen the later Canvas popup',not executions('pending-escape') and not any(e.get('case')=='pending-escape' for e in opens))
    add('Direct and blank OAuth chains continue in related views',bool(executions('oauth-direct-final')) and bool(executions('oauth-blank-final')) and not any(e.get('case','').startswith('oauth-') for e in opens))
    popup_errors=sorted({error for state in states for error in state.get('popupErrors',[])})
    add('Known login.live JS popup remains related and completes its provider redirect',bool(executions('login-live-popup-final')) and any(e.get('event')=='create-request-observed' and e.get('fixtureCase')=='login-live-popup' and e.get('navigationType')==5 and e.get('userGesture') is True for e in events))
    add('Trusted login.live main link stays in app through provider redirect',bool(executions('login-live-main')) and any(e.get('fixtureCase')=='login-live-main' and e.get('navigationType')==0 and e.get('userGesture') is True for e in events))
    add('Returning from login.live ends auth before automatic external navigation',bool(requests('login-live-return')) and not executions('post-login-live-return'))
    add('Popup references and cleanup succeeded',not popup_errors,popup_errors)
    add('Main auth redirect chain allowed its unknown provider response',bool(executions('main-auth-final')))
    add('Return to chat ended auth before the next automatic external navigation',bool(requests('main-auth-return')) and not executions('post-auth-return'))
    main_hops=[e for e in events if e.get('event')=='resource-sent-request' and e.get('fixtureCase') in ('main-auth-chain','main-auth-final') and e.get('redirectStatus')==302]
    add('Both auth redirects observed on one stable native main resource',len(main_hops)>=2 and len({e.get('resourceId') for e in main_hops})==1,main_hops)
    windows=[e.get('ownWebviewWindows') for e in events if e.get('event')=='own-window-count']
    add('Related popups closed and main window retained',bool(windows) and windows[0]==1 and max(windows)<=2 and windows[-1]==1,windows[-8:])
    return {'ok':all(c['passed'] for c in checks),'checks':checks,'finalFixtureState':final,
            'frameNameUsedAsMainFrameOracle':False,'nativeResponseMainFrameClassification':True,
            'applicationPolicyHandlersChanged':False,'realCanvasOrProviderLoginTested':False,
            'automaticPopupReachedNativeCreate':any(e.get('event')=='create-request-observed' and e.get('fixtureCase')=='auto-popup' for e in events),
            'limitations':['Controlled local HTTPS fixture; no real account, Canvas service or provider sign-in.',
                           'No automatic-popup native-create event can mean WebKit blocked it before the app; absence is not proof of the application popup gate.',
                           'A NavigationAction exposes gesture/type/target metadata, not a public main-frame flag. Native response classification is checked independently.',
                           'The private context uses a closed loopback CONNECT proxy and scoped test-certificate exceptions; no system trust or user profile is changed.']}
