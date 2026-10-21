"""Pure report fixtures: no browser, application, or user profile is started."""
import copy
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'active-frames' / 'run.py'
SPEC = importlib.util.spec_from_file_location('active_frame_report', SCRIPT)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def evidence(helper_disabled=False):
    """Complete observations with unequal CPU intervals and transition noise."""
    states, samples = [], []
    windows = [('visible', 8, 13), ('offscreen', 17, 25),
               ('hidden', 29, 37), ('returned', 41, 51)]
    for phase, start, end in windows:
        for seconds in (start, end):
            frames = [{
                'id': identity,
                'instance': 'document-' + str(identity),
                'sequence': seconds * 4,
                'raf': seconds * 60,
                'timers': seconds * 20,
                'visibility': 'visible',
                'inViewport': phase in ('visible', 'returned') or identity == 0,
                'draftPreserved': True,
            } for identity in range(8)]
            states.append({
                'phase': phase, 'elapsedMs': seconds * 1000,
                'sampledAtSeconds': seconds + .25,
                'helper': None if helper_disabled else {
                    'messages': 0, 'scans': 1, 'passes': 1,
                    'mutations': 0, 'measurements': 0, 'working': False,
                },
                'frames': frames,
            })
        first, last = start + .25, end + .25
        samples.extend([
            {'startSeconds': first - 1, 'endSeconds': first + .1,
             'cpuPercent': 9999, 'webProcesses': 1},
            {'startSeconds': first, 'endSeconds': first + 1,
             'cpuPercent': 20, 'webProcesses': 1},
            {'startSeconds': first + 1, 'endSeconds': last,
             'cpuPercent': 80, 'webProcesses': 1},
            {'startSeconds': last - .1, 'endSeconds': last + 1,
             'cpuPercent': 9999, 'webProcesses': 1},
        ])
    final = copy.deepcopy(states[-1])
    final.update(phase='stopped', elapsedMs=53000, sampledAtSeconds=53.25,
                 stopToken='current-stop-request')
    for frame in final['frames']:
        frame['stopAck'] = final['stopToken']
    states.append(final)
    return states, samples


class ActiveFrameReportTests(unittest.TestCase):
    def test_complete_phases_preserve_documents_drafts_and_time_weighted_cpu(self):
        for disabled in (False, True):
            with self.subTest(helper_disabled=disabled):
                states, samples = evidence(disabled)
                result = report.summarize(states, samples, disabled)
                self.assertTrue(result['allFrameDocumentsAndSyntheticDraftsPreserved'])
                self.assertEqual(set(result['phases']),
                                 {'visible', 'offscreen', 'hidden', 'returned'})
                visible = result['phases']['visible']
                self.assertEqual(visible['cpuSampleSeconds'], 5)
                # 20% for one second, then 80% for four seconds. Intervals
                # crossing the observation boundaries must not contribute.
                self.assertAlmostEqual(visible['webCpuMeanPercentOneCore'], 68)
                self.assertEqual(len(visible['frames']), 8)
                self.assertAlmostEqual(visible['frames'][0]['timerPerSecond'], 20)
                self.assertAlmostEqual(visible['frames'][0]['rafPerSecond'], 60)

    def test_missing_phase_is_rejected(self):
        states, samples = evidence()
        states = [s for s in states if s['phase'] != 'hidden']
        with self.assertRaisesRegex(ValueError, 'Missing settled samples for hidden'):
            report.summarize(states, samples)

    def test_snapshot_time_visible_samples_are_excluded(self):
        states, samples = evidence()
        early = copy.deepcopy(states[0])
        early.update(elapsedMs=5000, sampledAtSeconds=5.25)
        early['frames'] = []
        states.insert(0, early)
        # Keep an initial complete identity observation before snapshot noise.
        initial = copy.deepcopy(states[1])
        initial.update(elapsedMs=3000, sampledAtSeconds=3.25)
        states.insert(0, initial)
        result = report.summarize(states, samples)
        self.assertAlmostEqual(result['phases']['visible']['webCpuMeanPercentOneCore'], 68)

    def test_missing_frame_reports_are_rejected(self):
        states, samples = evidence()
        states[1]['frames'].pop()
        with self.assertRaisesRegex(ValueError, 'Missing frame reports'):
            report.summarize(states, samples)

    def test_missing_web_process_or_cpu_interval_is_rejected(self):
        for fault in ('zero_processes', 'no_matching_interval', 'too_short'):
            with self.subTest(fault=fault):
                states, samples = evidence()
                if fault == 'zero_processes':
                    samples[1]['webProcesses'] = 0
                elif fault == 'no_matching_interval':
                    samples = [{'startSeconds': 0, 'endSeconds': 100,
                                'cpuPercent': 12, 'webProcesses': 1}]
                else:
                    samples = [samples[1]]
                with self.assertRaisesRegex(ValueError, 'Insufficient web-process CPU coverage'):
                    report.summarize(states, samples)

    def test_requested_helper_presence_is_verified_in_both_directions(self):
        for disabled in (False, True):
            with self.subTest(helper_disabled=disabled):
                states, samples = evidence(disabled)
                states[1]['helper'] = {} if disabled else None
                with self.assertRaisesRegex(ValueError, 'Requested helper state was not observed'):
                    report.summarize(states, samples, disabled)

    def test_each_phase_requires_its_expected_viewport_distribution(self):
        for last_index in (1, 3, 5, 7):
            with self.subTest(phase=last_index):
                states, samples = evidence()
                frame = states[last_index]['frames'][1]
                frame['inViewport'] = not frame['inViewport']
                with self.assertRaisesRegex(ValueError, 'Incorrect viewport distribution'):
                    report.summarize(states, samples)

    def test_stale_frame_sequence_or_timer_is_rejected(self):
        for field in ('sequence', 'timers'):
            with self.subTest(field=field):
                states, samples = evidence()
                states[1]['frames'][3][field] = states[0]['frames'][3][field]
                with self.assertRaisesRegex(ValueError, 'No fresh frame progress'):
                    report.summarize(states, samples)

    def test_zero_offscreen_animation_is_valid_when_timer_reports_remain_fresh(self):
        states, samples = evidence()
        states[3]['frames'][3]['raf'] = states[2]['frames'][3]['raf']
        result = report.summarize(states, samples)
        frame = result['phases']['offscreen']['frames'][3]
        self.assertEqual(frame['rafPerSecond'], 0)
        self.assertGreater(frame['timerPerSecond'], 0)
        self.assertTrue(result['allFrameDocumentsAndSyntheticDraftsPreserved'])

    def test_document_replacement_during_phase_is_rejected(self):
        states, samples = evidence()
        states[3]['frames'][2]['instance'] = 'replacement-document'
        with self.assertRaisesRegex(ValueError, 'Frame was replaced during phase offscreen'):
            report.summarize(states, samples)

    def test_missing_or_wrong_final_stop_ack_cannot_pass_preservation(self):
        for fault in ('missing_ack', 'old_ack', 'missing_token', 'missing_frame'):
            with self.subTest(fault=fault):
                states, samples = evidence()
                final = states[-1]
                if fault == 'missing_ack':
                    final['frames'][4].pop('stopAck')
                elif fault == 'old_ack':
                    final['frames'][4]['stopAck'] = 'previous-stop-request'
                elif fault == 'missing_token':
                    final.pop('stopToken')
                else:
                    final['frames'].pop()
                result = report.summarize(states, samples)
                self.assertFalse(result['allFrameDocumentsAndSyntheticDraftsPreserved'])

    def test_changed_final_identity_or_lost_draft_cannot_pass_preservation(self):
        for fault in ('identity', 'draft'):
            with self.subTest(fault=fault):
                states, samples = evidence()
                frame = states[-1]['frames'][5]
                if fault == 'identity':
                    frame['instance'] = 'replacement-document'
                else:
                    frame['draftPreserved'] = False
                result = report.summarize(states, samples)
                self.assertFalse(result['allFrameDocumentsAndSyntheticDraftsPreserved'])


if __name__ == '__main__':
    unittest.main()
