import unittest
from leanplan.desktop import fit_window_bounds, CANVAS_WIDTH, CANVAS_HEIGHT


class GeometryTests(unittest.TestCase):
    def test_work_area_and_windows_frame_are_respected_across_dpi(self):
        cases=[(1366,720,96),(1280,672,120),(1920,1040,120),(1920,1040,192),
               (2560,1392,144),(3840,2112,192),(3440,1392,120)]
        for width,height,dpi in cases:
            for left in (0,-width):
                with self.subTest(size=(width,height),dpi=dpi,left=left):
                    fw,fh=round(2*dpi/96),round(31*dpi/96)
                    result=fit_window_bounds((left,40,width,height),dpi,fw,fh)
                    self.assertGreaterEqual(result.x,left+result.margin)
                    self.assertGreaterEqual(result.y,40+result.margin)
                    self.assertLessEqual(result.x+result.width,left+width-result.margin)
                    self.assertLessEqual(result.y+result.height,40+height-result.margin)
                    self.assertEqual(result.width-result.client_width,fw)
                    self.assertEqual(result.height-result.client_height,fh)
                    self.assertLess(abs(result.client_width/CANVAS_WIDTH-result.client_height/CANVAS_HEIGHT),.002)

    def test_larger_displays_receive_a_larger_uniform_window(self):
        small=fit_window_bounds((0,0,1366,720))
        large=fit_window_bounds((0,0,3840,2112),192,4,62)
        self.assertGreater(large.width,small.width*2)
        self.assertGreater(large.height,small.height*2)

    def test_qhd_at_100_percent_is_approximately_a_quarter_screen(self):
        result=fit_window_bounds((0,0,2560,1392),96,16,39)
        self.assertEqual((result.client_width,result.client_height),(1200,780))
        self.assertAlmostEqual(result.width*result.height/(2560*1440),.25,delta=.025)

    def test_dip_size_does_not_expand_to_fill_large_monitors(self):
        qhd=fit_window_bounds((0,0,2560,1392),96,16,39)
        uhd=fit_window_bounds((0,0,3840,2112),96,16,39)
        self.assertEqual((qhd.width,qhd.height),(uhd.width,uhd.height))
        scaled=fit_window_bounds((0,0,3840,2112),144,24,59)
        self.assertEqual((scaled.client_width,scaled.client_height),(1800,1170))


if __name__=='__main__':unittest.main()
