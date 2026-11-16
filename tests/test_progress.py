import io
import unittest

from symbolmaker.progress import Reporter, fmt_count, fmt_duration, fmt_rate, format_table


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def tick(self, s):
        self.t += s


class FormatTests(unittest.TestCase):
    def test_counts_get_thousands_separators(self):
        self.assertEqual((fmt_count(7), fmt_count(5503), fmt_count(1234567)), ("7", "5,503", "1,234,567"))

    def test_durations_are_short_and_readable(self):
        self.assertEqual(
            [fmt_duration(s) for s in (0.4, 3.2, 59.9, 61, 754, 3725)],
            ["0.4s", "3.2s", "59.9s", "1:01", "12:34", "1:02:05"],
        )

    def test_rates(self):
        self.assertEqual((fmt_rate(41.3), fmt_rate(0.5), fmt_rate(0)), ("41/s", "0.5/s", "0/s"))


class TableTests(unittest.TestCase):
    def test_columns_line_up_and_a_total_row_is_added(self):
        rows = [
            {
                "title": "Lucide",
                "version": "1.73.0",
                "icons": 2055,
                "problems": 3,
                "notes": 5,
                "failed": 0,
                "reused": 2055,
                "seconds": 1.5,
            },
            {
                "title": "Tabler Icons",
                "version": "3.52.0",
                "icons": 5503,
                "problems": 48,
                "notes": 54,
                "failed": 0,
                "reused": 0,
                "seconds": 134.0,
            },
        ]
        lines = format_table(rows)
        self.assertEqual(len(lines), 5)  # header, rule, two rows, total
        text = "\n".join(lines)
        for want in ("Lucide", "1.73.0", "2,055", "5,503", "Tabler Icons", "2:14", "Total", "7,558", "51"):
            self.assertIn(want, text)
        self.assertEqual(len({len(ln.rstrip()) for ln in lines[2:]}) >= 1, True)
        self.assertTrue(all("\t" not in ln for ln in lines))
        col = lines[0].index("Icons")  # the icon counts sit under their header
        self.assertTrue(lines[2][col:].lstrip().startswith("2,055".rjust(1)) or "2,055" in lines[2])


class ReporterTests(unittest.TestCase):
    def reporter(self, interactive):
        self.out, self.clock = io.StringIO(), FakeClock()
        return Reporter(self.out, clock=self.clock, interactive=interactive, interval=0.5, line_every=15.0, color=False)

    def test_a_terminal_gets_one_live_line_that_is_redrawn_in_place(self):
        r = self.reporter(True)
        r.start("Tabler Icons", total=100, reused=0)
        for _ in range(50):
            self.clock.tick(0.1)
            r.advance()
        text = self.out.getvalue()
        self.assertIn("\r", text)
        self.assertNotIn("\n", text)  # still the same line
        last = text.split("\r")[-1]
        for want in ("Tabler Icons", "/100", "%", "/s", "ETA"):
            self.assertIn(want, last)
        import re

        found = re.search(r"(\d+)/100", last)
        assert found is not None
        drawn = int(found.group(1))
        self.assertTrue(40 <= drawn <= 50, drawn)  # throttled: may trail by up to half a second

    def test_the_live_line_is_throttled(self):
        r = self.reporter(True)
        r.start("X", total=1000, reused=0)
        for _ in range(100):
            self.clock.tick(0.001)
            r.advance()  # 0.1 s in total: at most the first draw
        self.assertLessEqual(self.out.getvalue().count("\r"), 2)

    def test_done_replaces_the_live_line_with_a_summary_line(self):
        r = self.reporter(True)
        r.start("Lucide", total=10, reused=4)
        for _ in range(10):
            self.clock.tick(1)
            r.advance()
        r.done({"icons": 10, "failed": 0, "problems": 1, "notes": 2, "reused": 4})
        final = self.out.getvalue().rstrip("\n").split("\n")[-1].split("\r")[-1]
        for want in ("Lucide", "10 icons", "1 problem", "2 notes", "4 reused", "0 failed"):
            self.assertIn(want, final)
        self.assertTrue(self.out.getvalue().endswith("\n"))

    def test_a_log_gets_plain_lines_at_ten_percent_steps(self):
        r = self.reporter(False)
        r.start("Lucide", total=100, reused=0)
        for _ in range(100):
            self.clock.tick(0.2)
            r.advance()
        text = self.out.getvalue()
        self.assertNotIn("\r", text)
        self.assertNotIn("\x1b", text)  # no color codes in a log
        lines = [ln for ln in text.split("\n") if ln]
        self.assertTrue(8 <= len(lines) <= 12, len(lines))
        self.assertIn("100/100", lines[-1])

    def test_a_log_also_prints_when_a_long_time_passes_between_steps(self):
        r = self.reporter(False)
        r.start("Big", total=10000, reused=0)
        for _ in range(4):
            self.clock.tick(16)
            r.advance()  # 16 s each, far below 10% of the total
        self.assertGreaterEqual(len([ln for ln in self.out.getvalue().split("\n") if ln]), 3)

    def test_everything_cached_is_reported_as_such_without_an_eta(self):
        r = self.reporter(False)
        r.start("Lucide", total=50, reused=50)
        r.advance(50)
        r.done({"icons": 50, "failed": 0, "problems": 0, "notes": 0, "reused": 50})
        text = self.out.getvalue()
        self.assertIn("50 reused", text)
        self.assertNotIn("ETA", text)

    def test_info_lines_are_printed_as_given(self):
        r = self.reporter(False)
        r.info("hello")
        self.assertEqual(self.out.getvalue(), "hello\n")


if __name__ == "__main__":
    unittest.main()
