import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from choruko import collector, market, rules
from choruko import __main__ as cli


def snap(closes, code="8035"):
    return market.StockSnapshot(code, list(closes), [100] * len(closes))


class Indicators(unittest.TestCase):
    def test_rsi_extremes(self):
        self.assertEqual(market.rsi(list(range(1, 30))), 100.0)
        self.assertLess(market.rsi(list(range(30, 1, -1))), 1.0)
        self.assertIsNone(market.rsi([1, 2, 3]))

    def test_drawdown_and_ma(self):
        s = snap([100] * 30 + [90])
        self.assertAlmostEqual(s.drawdown_20d, -10.0)
        self.assertLess(s.ma25_dev, -9)


class Regime(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(rules.classify_regime(fg=15), "panic")
        self.assertEqual(rules.classify_regime(fg=50, nvi=45), "panic")
        self.assertEqual(rules.classify_regime(fg=30), "fear")
        self.assertEqual(rules.classify_regime(fg=50, vix=32), "fear")
        self.assertEqual(rules.classify_regime(fg=70, nvi=20), "greed")
        self.assertEqual(rules.classify_regime(fg=50, nvi=24), "neutral")
        self.assertIsNone(rules.classify_regime())


STOCK = rules.Stock("8035", "東京エレクトロン", "半導体製造装置", True, ["AI・半導体"])


class Screen(unittest.TestCase):
    def test_oversold_leader_scores(self):
        c = rules.evaluate(STOCK, snap([100] * 40 + [88]), themes=["AI・半導体"])
        self.assertGreater(c.score, 4)
        plan = c.plan()
        self.assertEqual(plan["stop"], 79.2)  # -10%
        self.assertGreater(plan["target_ma25"], 88)

    def test_not_cheap_is_not_candidate(self):
        c = rules.evaluate(STOCK, snap([100 + i for i in range(40)]))
        self.assertEqual(c.score, 0)
        self.assertEqual(rules.rank([c]), [])

    def test_position_stop_and_take_profit(self):
        p = {"code": "8035", "entry": 100, "shares": 100, "wallet": "attack"}
        self.assertIn("損切り", rules.check_position(p, snap([100] * 30 + [89]), "fear")["actions"][0])
        tp = rules.check_position(p, snap([100] * 30 + [110]), "greed")["actions"]
        self.assertTrue(any("25日線" in x for x in tp) and any("強欲" in x for x in tp))
        d = dict(p, wallet="defense")
        self.assertEqual(rules.check_position(d, snap([100] * 30 + [110]), "greed")["actions"], ["保有継続"])

    def test_universe_loads(self):
        u = rules.load_universe()
        self.assertGreater(len(u), 30)
        self.assertTrue(any(s.code == "8035" and s.leader for s in u))


RSS = """<rss><channel>
<item><title>ちょる子さんが語る暴落の買い方</title><link>https://ex.com/a</link>
<pubDate>Mon, 05 Oct 2026 01:00:00 GMT</pubDate><description>&lt;b&gt;恐怖指数&lt;/b&gt;で判断</description></item>
<item><title>無関係な記事</title><link>https://ex.com/b</link><description>株</description></item>
</channel></rss>"""


class Collector(unittest.TestCase):
    def test_parse_rss_filters_and_strips(self):
        items = collector.parse_rss(RSS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "恐怖指数 で判断")
        self.assertTrue(items[0]["published"].startswith("2026-10-05"))

    def test_append_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            items = collector.parse_rss(RSS)
            self.assertEqual(collector.append_sources(items, path), 1)
            self.assertEqual(collector.append_sources(items, path), 0)


class CliOffline(unittest.TestCase):
    """ネットに出ずに screen と suggest --no-ai が最後まで動くこと。"""

    def test_screen_runs(self):
        def fake_daily(code, range_="6mo"):
            return snap([100] * 40 + [88], code) if code == "8035" else snap([100] * 41, code)
        with mock.patch.object(market, "fetch_daily", fake_daily), \
             mock.patch.object(market, "fetch_fear_greed", lambda: {"score": 18, "rating": "extreme fear"}), \
             mock.patch.object(market, "fetch_nikkei_vi", lambda: 33.0), \
             mock.patch.object(cli, "load_positions", lambda: []), \
             mock.patch("builtins.print") as out:
            cli.main(["suggest", "--no-ai"])
        text = "\n".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertIn('"regime": "panic"', text)
        self.assertIn("8035 東京エレクトロン", text)


if __name__ == "__main__":
    unittest.main()
