"""Guard against a native callback being mistaken for an allowed frame request."""
import copy
import unittest
import run


def evidence(fixed):
    events = [
        *({'event': 'observer-installed', 'signal': name, 'hookInstalled': True}
          for name in ('decide-policy', 'create')),
        {'event': 'controlled-html-replacement'},
        {'event': 'fixture-state', 'ownFixtureState': {
            'controlledFixture': True, 'finished': True, 'origin': 'https://chat.mistral.ai',
            'popupAttempted': True, 'popupReturnedNull': True, 'popupEventTrusted': True}},
        {'event': 'native-click-dispatched', 'scopedToOwnWebview': True},
        {'event': 'own-window-count', 'ownWebviewWindows': 1},
        {'event': 'create-request-observed', 'fixtureCase': 'challenge-popup', 'origin': run.CF},
    ]
    opens = [{'fixtureCase': 'external-normal', 'origin': 'https://example.com', 'browserStarted': False}]
    for case in run.FRAME_CASES:
        events.append({'event': 'policy-observed', 'type': 'navigation-action', 'fixtureCase': case, 'origin': run.CF})
        if fixed:
            events.append({'event': 'resource-load-started', 'fixtureCase': case, 'origin': run.CF})
    if not fixed:
        opens.extend({'fixtureCase': case, 'origin': run.CF, 'cloudflareChallenge': True, 'browserStarted': False}
                     for case in (*run.FRAME_CASES, 'challenge-popup'))
    return events, opens


class ReportTests(unittest.TestCase):
    def test_observed_navigation_alone_does_not_pass_fixed_contract(self):
        events, opens = evidence(False)
        result = run.check_report(events, opens, 'fixed')
        self.assertFalse(result['ok'])
        self.assertFalse(result['fixedContractPassed'])

    def test_old_control_is_explicitly_a_failed_fixed_contract(self):
        events, opens = evidence(False)
        result = run.check_report(events, opens, 'old')
        self.assertTrue(result['ok'])
        self.assertFalse(result['fixedContractPassed'])

    def test_actual_resource_starts_are_required_for_every_frame(self):
        events, opens = evidence(True)
        self.assertTrue(run.check_report(events, opens, 'fixed')['ok'])
        events = [event for event in events if not (event.get('event') == 'resource-load-started'
                  and event.get('fixtureCase') == 'named')]
        self.assertFalse(run.check_report(events, opens, 'fixed')['ok'])

    def test_main_frame_response_or_extra_window_fails(self):
        events, opens = evidence(True)
        other = copy.deepcopy(events)
        other.append({'event': 'policy-observed', 'type': 'response', 'fixtureCase': 'named',
                      'origin': run.CF, 'mainFrameMainResource': True, 'httpStatus': 404})
        self.assertFalse(run.check_report(other, opens, 'fixed')['ok'])
        events.append({'event': 'own-window-count', 'ownWebviewWindows': 2})
        self.assertFalse(run.check_report(events, opens, 'fixed')['ok'])


if __name__ == '__main__':
    unittest.main()
