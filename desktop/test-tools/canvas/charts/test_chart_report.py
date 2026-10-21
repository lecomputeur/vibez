import copy
import unittest
from chart_report import BLUE,check_chart

def ready():
    return {'chartCount':8,'ready':list(reversed(range(8))),'attempts':[1]*8,
            'scriptMessages':8,'validatedPixels':[BLUE]*8,'tableRows':4,'finished':True}

class ChartReportTests(unittest.TestCase):
    def test_ready_order_is_not_a_completion_oracle(self):
        self.assertTrue(check_chart(ready(),8,'fixed')['expectedStatePassed'])

    def test_load_events_and_ready_counter_without_pixels_do_not_pass(self):
        s=ready();s['validatedPixels']=[];s['frameLoadEvents']=100
        self.assertFalse(check_chart(s,8,'fixed')['expectedStatePassed'])

    def test_wrong_pixel_missing_script_or_missing_chart_fails(self):
        for key,value in [('validatedPixels',[[0,0,0,0]]*8),('scriptMessages',7),('ready',list(range(7)))]:
            s=ready();s[key]=value
            self.assertFalse(check_chart(s,8,'fixed')['expectedStatePassed'])

    def test_old_control_pass_is_not_a_successful_render(self):
        s=ready();s.update(ready=[],attempts=[20]*8,scriptMessages=0,validatedPixels=[])
        r=check_chart(s,8,'old')
        self.assertTrue(r['expectedStatePassed']);self.assertFalse(r['fixedContractPassed'])
        self.assertFalse(check_chart(s,8,'fixed')['expectedStatePassed'])

    def test_unfinished_run_and_recurring_retry_fail_fixed(self):
        for key,value in [('finished',False),('attempts',[2]*8)]:
            s=ready();s[key]=value
            self.assertFalse(check_chart(s,8,'fixed')['expectedStatePassed'])

if __name__=='__main__':unittest.main()
