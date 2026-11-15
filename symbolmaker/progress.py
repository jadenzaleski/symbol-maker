"""Terminal output for the site build: live progress with rate and ETA, per-source results and a summary table.

On a terminal each source gets one line that is redrawn in place (about twice a second); in a log (CI, a pipe) it prints
a plain line at every 10% and whenever 15 seconds have passed, with no control characters.
"""
import os
import sys
import time

BAR = 20


def fmt_count(n):
    return f'{n:,}'


def fmt_duration(s):
    if s < 60:
        return f'{s:.1f}s'
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'


def fmt_rate(per_second):
    return f'{per_second:.0f}/s' if per_second >= 10 else f'{per_second:.1f}/s'.replace('.0/s', '/s')


def _plural(n, word, plural=None):
    return f'{fmt_count(n)} {word if n == 1 else (plural or word + "s")}'


def format_table(rows):
    """Lines of an aligned table, one row per source plus a total. Each row: title, version, icons, problems, notes,
    failed, reused, seconds."""
    head = ('Source', 'Version', 'Icons', 'Problems', 'Notes', 'Failed', 'Reused', 'Time')
    body = [(r['title'], r['version'], fmt_count(r['icons']), fmt_count(r['problems']), fmt_count(r['notes']),
             fmt_count(r['failed']), fmt_count(r['reused']), fmt_duration(r['seconds'])) for r in rows]
    tot = ('Total', '', fmt_count(sum(r['icons'] for r in rows)), fmt_count(sum(r['problems'] for r in rows)),
           fmt_count(sum(r['notes'] for r in rows)), fmt_count(sum(r['failed'] for r in rows)),
           fmt_count(sum(r['reused'] for r in rows)), fmt_duration(sum(r['seconds'] for r in rows)))
    widths = [max(len(row[i]) for row in [head, *body, tot]) for i in range(len(head))]

    def line(row):
        cells = [row[0].ljust(widths[0]), row[1].ljust(widths[1])] + [c.rjust(w) for c, w in zip(row[2:], widths[2:])]
        return '  ' + '  '.join(cells)

    return [line(head), '  ' + '  '.join('-' * w for w in widths), *[line(r) for r in body], line(tot)]


class Reporter:
    def __init__(self, stream=None, clock=time.monotonic, interactive=None, interval=0.5, line_every=15.0, color=None):
        self.out = stream or sys.stdout
        self.clock = clock
        self.interactive = self.out.isatty() if interactive is None else interactive
        self.interval, self.line_every = interval, line_every
        self.color = (self.interactive and not os.environ.get('NO_COLOR')) if color is None else color
        self._title = None

    def _c(self, code, text):
        return f'\x1b[{code}m{text}\x1b[0m' if self.color else text

    def info(self, text=''):
        self.out.write(text + '\n')
        self.out.flush()

    # ---- one source ----
    def start(self, title, total, reused=0):
        self._title, self._total, self._reused = title, total, reused
        self._done, self._t0 = 0, self.clock()
        self._last_draw = self._last_line = None
        self._next_pct = 10

    def advance(self, n=1):
        self._done += n
        now = self.clock()
        if self.interactive:
            if self._last_draw is None or now - self._last_draw >= self.interval or self._done >= self._total:
                self._last_draw = now
                self.out.write('\r\x1b[2K' + self._live_line(now))
                self.out.flush()
            return
        pct = 100 * self._done // max(self._total, 1)
        quiet_for = now - (self._last_line if self._last_line is not None else self._t0)
        if pct >= self._next_pct or quiet_for >= self.line_every or self._done >= self._total:
            while self._next_pct <= pct:
                self._next_pct += 10
            self._last_line = now
            self.out.write(self._live_line(now) + '\n')
            self.out.flush()

    def _live_line(self, now):
        total = max(self._total, 1)
        filled = BAR * self._done // total
        bar = '█' * filled + '░' * (BAR - filled)
        made = self._done - self._reused                                      # icons converted this run
        elapsed = max(now - self._t0, 1e-9)
        width = len(fmt_count(self._total))
        text = f'  {self._title:<14} {bar} {fmt_count(self._done):>{width}}/{fmt_count(self._total)}  {100 * self._done // total:3d}%'
        if made > 0 and elapsed > 0.2:
            rate = made / elapsed
            remaining = max(self._total - self._done, 0)
            text += f'  {fmt_rate(rate)}  ETA {fmt_duration(remaining / rate)}' if remaining else f'  {fmt_rate(rate)}'
        return text

    def done(self, stats):
        seconds = self.clock() - self._t0
        made = stats['icons'] + stats['failed'] - stats['reused']
        parts = [_plural(stats['icons'], 'icon'), _plural(stats['problems'], 'problem'), _plural(stats['notes'], 'note'),
                 f'{fmt_count(stats["failed"])} failed', f'{fmt_count(stats["reused"])} reused']
        speed = f' ({fmt_rate(made / seconds)})' if made > 0 and seconds > 0 else ''
        mark = self._c('32', '✓') if not stats['failed'] else self._c('33', '!')
        line = f'  {mark} {self._title:<14} ' + ' · '.join(parts) + f' · {fmt_duration(seconds)}{speed}'
        self.out.write(('\r\x1b[2K' if self.interactive else '') + line + '\n')
        self.out.flush()
        return seconds

    def table(self, rows):
        for line in format_table(rows):
            self.info(line)


class NullReporter:
    """Same calls, no output (the default for build())."""
    def info(self, text=''): pass
    def start(self, *a, **k): pass
    def advance(self, n=1): pass
    def done(self, stats): return 0.0
    def table(self, rows): pass
