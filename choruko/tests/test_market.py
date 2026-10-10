import unittest

from choruko import market

# 日経VIのプロファイルページ（2026-10-10 取得）から、値の周辺だけを抜粋したもの
NVI_HTML = """
<div class="individual-value">
    <div>
        <div class="current" id="price"><!--daily_changing-->30.14</div>
        <div class="daily-change up" id="updown_class">
            <span class="range" id="rate"><!--daily_changing-->+1.86%</span>
"""


class NikkeiVi(unittest.TestCase):
    def test_reads_value_after_comment(self):
        self.assertEqual(market.parse_nikkei_vi(NVI_HTML), 30.14)

    def test_reads_plain_value(self):
        self.assertEqual(market.parse_nikkei_vi('<div id="price">1,234.5</div>'), 1234.5)

    def test_raises_when_missing(self):
        with self.assertRaises(ValueError):
            market.parse_nikkei_vi("<html></html>")


if __name__ == "__main__":
    unittest.main()
