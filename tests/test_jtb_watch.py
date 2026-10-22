"""jtb_watch の単体テスト（ネットに出ない）。
fixtures/ の HTML は、2026-10-22 に本物のページを Chrome で開いた描画後の HTML から、
更新情報欄とクーポン欄だけを切り出したもの（全カード配布終了の状態）。

実行: python -m unittest discover -s tests -t .
"""
import os
import tempfile
import unittest

import jtb_watch

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def revive(html, n):
    """n 枚目（ページ全体で1始まり）のカードから c-close を外し、ページ側の全終了の印も外す。"""
    html = html.replace("l-entry karte-close", "l-entry")
    parts = html.split('class="c-coupon__data c-close"')
    return 'class="c-coupon__data c-close"'.join(parts[:n]) + 'class="c-coupon__data"' + \
        'class="c-coupon__data c-close"'.join(parts[n:])


class ParsePageTest(unittest.TestCase):
    def test_kumamoto_structure(self):
        page = jtb_watch.parse_page(load("jtb_kumamoto_closed.html"))
        cards = page["cards"]
        self.assertEqual(len(cards), 15)
        self.assertTrue(all(c["closed"] for c in cards))
        sections = list(dict.fromkeys(c["section"] for c in cards))
        self.assertEqual(sections, ["【宿泊】泊数指定なし", "【飛行機利用・JR利用】1泊限定",
                                    "【飛行機利用・JR利用】2泊以上"])
        first = cards[0]
        self.assertEqual((first["no"], first["name"], first["count"]), (1, "【宿泊】1名", "先着 350枚"))
        self.assertEqual((first["code"], first["password"]), ("ZSKMM", "W266"))
        self.assertIn("60 ％引", first["price"])
        self.assertIn("割引上限20,000円", first["price"])
        # 区分ごとに 1枚目から数え直す
        self.assertEqual([c["no"] for c in cards], [1, 2, 3, 4, 5] * 3)
        self.assertTrue(page["updates"][0].startswith("2026/10/22"))

    def test_miyazaki_has_two_sections(self):
        cards = jtb_watch.parse_page(load("jtb_miyazaki_closed.html"))["cards"]
        self.assertEqual(len(cards), 10)
        self.assertEqual(cards[0]["section"], "【飛行機利用・JR利用】1泊限定")

    def test_one_card_open(self):
        cards = jtb_watch.parse_page(revive(load("jtb_kagoshima_closed.html"), 7))["cards"]
        opened = [c for c in cards if not c["closed"]]
        self.assertEqual(len(opened), 1)
        self.assertEqual((opened[0]["section"], opened[0]["no"]), ("【飛行機利用・JR利用】1泊限定", 2))

    def test_page_level_close_marks_all(self):
        # ページ側の karte-close があれば、カードに c-close が無くても終了扱い
        html = load("jtb_kumamoto_closed.html").replace("c-coupon__data c-close", "c-coupon__data")
        self.assertTrue(all(c["closed"] for c in jtb_watch.parse_page(html)["cards"]))


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.html = load("jtb_kumamoto_closed.html")
        self.closed = jtb_watch.parse_page(self.html)

    def test_no_change(self):
        self.assertEqual(jtb_watch.diff_pages(self.closed, jtb_watch.parse_page(self.html)), [])

    def test_revive_and_end(self):
        opened = jtb_watch.parse_page(revive(self.html, 2))
        ev = jtb_watch.diff_pages(self.closed, opened)
        self.assertEqual(len(ev), 1)
        judge, section, no, detail = ev[0]
        self.assertEqual((judge, section, no), ("復活", "【宿泊】泊数指定なし", 2))
        self.assertIn("【宿泊】2名", detail)
        self.assertIn("コード ZSKMM / パスワード W267", detail)
        ev = jtb_watch.diff_pages(opened, self.closed)
        self.assertEqual([e[:3] for e in ev], [("終了", "【宿泊】泊数指定なし", 2)])

    def test_count_change_is_reported(self):
        changed = jtb_watch.parse_page(self.html.replace("先着 350枚", "先着 400枚"))
        ev = jtb_watch.diff_pages(self.closed, changed)
        self.assertEqual([e[:3] for e in ev], [("内容変更", "【宿泊】泊数指定なし", 1)])
        self.assertIn("先着 350枚", ev[0][3])
        self.assertIn("先着 400枚", ev[0][3])

    def test_update_info(self):
        changed = jtb_watch.parse_page(self.html.replace(
            "<ul>", '<ul><li><span class="c-date">2026/10/23</span>枚数を追加いたしました。</li>', 1))
        ev = jtb_watch.diff_pages(self.closed, changed)
        self.assertEqual(ev[0][0], "更新情報")
        self.assertIn("2026/10/23", ev[0][3])


class FakeBrowser:
    def __init__(self, pages):
        self.pages = list(pages)

    def get(self, url):
        return self.pages.pop(0)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, message, url=None, priority=4):
        self.sent.append((title, message, priority))


class WatcherTest(unittest.TestCase):
    def test_revive_is_recorded_and_notified(self):
        closed = load("jtb_kumamoto_closed.html")
        opened = revive(closed, 2)
        with tempfile.TemporaryDirectory() as d:
            notifier, recorder = FakeNotifier(), jtb_watch.Recorder(d)
            w = jtb_watch.Watcher("熊本", "http://example/", notifier, recorder)
            # 1回目: 基準 / 2回目: 変化なし / 3回目: 復活（確認のためもう1回読む）
            browser = FakeBrowser([closed, closed, opened, opened])
            for _ in range(3):
                self.assertTrue(w.check(browser))
            self.assertEqual(len(notifier.sent), 1)
            title, message, priority = notifier.sent[0]
            self.assertEqual(title, "【復活】JTB 熊本")
            self.assertTrue(message.startswith("【宿泊】泊数指定なし 2枚目 復活 / 【宿泊】2名"))
            self.assertEqual(priority, 5)
            with open(os.path.join(d, "events.csv"), encoding="utf-8-sig") as f:
                rows = f.read().splitlines()
            self.assertEqual(len(rows), 2)
            self.assertIn("熊本,復活,【宿泊】泊数指定なし,2,", rows[1])
            self.assertEqual(len(os.listdir(os.path.join(d, "snapshots"))), 1)

    def test_unmarked_page_is_not_revival(self):
        # 終了の印が1枚も無いページ（KARTE が働かなかった）は全部配布中と読まない
        closed = load("jtb_kumamoto_closed.html")
        unmarked = closed.replace("l-entry karte-close", "l-entry").replace(
            "c-coupon__data c-close", "c-coupon__data")
        with tempfile.TemporaryDirectory() as d:
            notifier = FakeNotifier()
            shared = {"marks_seen": False}
            w = jtb_watch.Watcher("長崎", "http://example/", notifier, jtb_watch.Recorder(d), shared)
            browser = FakeBrowser([unmarked, closed, unmarked, unmarked, unmarked, unmarked])
            for _ in range(6):
                self.assertTrue(w.check(browser))
            # 基準は印のある回から取る。印の無い状態が3回続いたら「要確認」を1回だけ
            self.assertEqual([t for t, _, _ in notifier.sent], ["【要確認】JTB 長崎"])
            self.assertTrue(all(c["closed"] for c in w.state["cards"]))

    def test_unmarked_everywhere_says_cannot_judge(self):
        closed = load("jtb_kumamoto_closed.html")
        unmarked = closed.replace("l-entry karte-close", "l-entry").replace(
            "c-coupon__data c-close", "c-coupon__data")
        with tempfile.TemporaryDirectory() as d:
            notifier = FakeNotifier()
            w = jtb_watch.Watcher("長崎", "http://example/", notifier, jtb_watch.Recorder(d))
            browser = FakeBrowser([unmarked] * 4)
            for _ in range(4):
                w.check(browser)
            self.assertEqual([t for t, _, _ in notifier.sent], ["JTB 長崎 判定できません"])
            self.assertIsNone(w.state)

    def test_revive_confirm_unmarked_is_ignored(self):
        closed = load("jtb_kumamoto_closed.html")
        unmarked = closed.replace("l-entry karte-close", "l-entry").replace(
            "c-coupon__data c-close", "c-coupon__data")
        with tempfile.TemporaryDirectory() as d:
            notifier = FakeNotifier()
            w = jtb_watch.Watcher("熊本", "http://example/", notifier, jtb_watch.Recorder(d))
            w.check(FakeBrowser([closed]))
            w.check(FakeBrowser([revive(closed, 2), unmarked]))
            self.assertEqual(notifier.sent, [])

    def test_revive_not_confirmed_is_ignored(self):
        # 1回だけ開いて見えて、確認で消えていたら通知しない
        closed = load("jtb_kumamoto_closed.html")
        with tempfile.TemporaryDirectory() as d:
            notifier = FakeNotifier()
            w = jtb_watch.Watcher("熊本", "http://example/", notifier, jtb_watch.Recorder(d))
            browser = FakeBrowser([closed, revive(closed, 2), closed])
            w.check(browser)
            w.check(browser)
            self.assertEqual(notifier.sent, [])
            self.assertFalse(os.path.exists(os.path.join(d, "events.csv")))


if __name__ == "__main__":
    unittest.main()
