import copy
import unittest
import run


def evidence(scenario):
    target='https://canvas.mistralusercontent.com' if scenario=='canvas' else 'https://accounts.google.com'
    events=[
        {'event':'fixture-state','ownFixtureState':{'controlledFixture':True,'scenario':scenario,'finished':True,'popupEventTrusted':True,'popupReturnedNull':False,'bootstrapMessages':1,'srcdocMessages':1}},
        {'event':'policy-observed','fixtureCase':'unnamed','origin':'https://challenges.cloudflare.com'},
        {'event':'resource-load-started','fixtureCase':'unnamed','origin':'https://challenges.cloudflare.com'},
        {'event':'resource-load-started','fixtureCase':'preview-popup','origin':target},
        {'event':'auxiliary-probe','probe':{'nativeIPC':'denied','openerPresent':True}},
    ]
    opens=[]
    if scenario=='canvas':opens.append({'fixtureCase':'external-normal','browserStarted':False})
    else:events.append({'event':'resource-load-started','fixtureCase':'external-normal','origin':'https://example.com'})
    return events,opens


class BootstrapReportTests(unittest.TestCase):
    def test_canvas_and_oauth_each_pass_their_distinct_contract(self):
        for scenario in ['canvas','oauth']:
            events,opens=evidence(scenario)
            self.assertTrue(run.check_report(events,opens,'fixed')['ok'])

    def test_canvas_does_not_pass_after_becoming_generic_auth(self):
        events,opens=evidence('canvas')
        events.append({'event':'resource-load-started','fixtureCase':'external-normal','origin':'https://example.com'})
        self.assertFalse(run.check_report(events,[],'fixed')['ok'])

    def test_oauth_does_not_pass_when_limited_to_canvas(self):
        events,opens=evidence('oauth')
        events=[e for e in events if e.get('fixtureCase')!='external-normal']
        self.assertFalse(run.check_report(events,[{'fixtureCase':'external-normal','browserStarted':False}],'fixed')['ok'])

    def test_native_callback_does_not_substitute_for_a_started_challenge_request(self):
        events,opens=evidence('canvas')
        events=[e for e in events if not(e.get('event')=='resource-load-started' and e.get('fixtureCase')=='unnamed')]
        self.assertFalse(run.check_report(events,opens,'fixed')['ok'])

    def test_srcdoc_script_and_no_successful_native_state_are_required(self):
        events,opens=evidence('canvas');bad=copy.deepcopy(events)
        bad[0]['ownFixtureState']['srcdocMessages']=0
        self.assertFalse(run.check_report(bad,opens,'fixed')['ok'])
        events.append({'event':'auxiliary-probe','probe':{'nativeIPC':'UNSAFE','openerPresent':True}})
        self.assertFalse(run.check_report(events,opens,'fixed')['ok'])


if __name__=='__main__':unittest.main()
