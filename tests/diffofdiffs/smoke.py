"""Exercise the installed CLI, embedded HTML and read-only Git tree mode."""

import os
from pathlib import Path
import subprocess
import tempfile


def run(arguments, **kwargs):
    return subprocess.check_output(arguments, text=True, **kwargs)


assert '1.1.0' in run(['diffofdiffs', '--version'])
with tempfile.TemporaryDirectory(prefix='diffofdiffs-installed-') as directory:
    root = Path(directory)
    for name in ['left', 'right']:
        (root / f'{name}.patch').write_text(
            f'--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+{name}\n')
    operands = [str(root / 'left.patch'), str(root / 'right.patch')]
    report = run(['diffofdiffs', *operands])
    assert 'left' in report and 'right' in report
    html = root / 'report.html'
    run(['diffofdiffs', '--html', '-o', str(html), *operands])
    text = html.read_text()
    assert '<html' in text and '<script' in text and 'left' in text and 'right' in text
    repository = root / 'repository'
    environment = {**os.environ, 'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                   'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}

    def git(*arguments):
        return run(['git', '-C', str(repository), *arguments], env=environment).strip()

    repository.mkdir()
    git('init', '--quiet')
    source = repository / 'file'
    source.write_text('old\n')
    git('add', 'file')
    git('commit', '--quiet', '-m', 'base')
    base = git('rev-parse', 'HEAD')
    source.write_text('left\n')
    git('commit', '--quiet', '-am', 'left')
    left = git('rev-parse', 'HEAD')
    git('checkout', '--quiet', base)
    source.write_text('right\n')
    git('commit', '--quiet', '-am', 'right')
    right = git('rev-parse', 'HEAD')
    index = (repository / '.git/index').read_bytes()
    report = run(['diffofdiffs', '--git-tree=' + str(repository), left, right])
    assert 'left' in report and 'right' in report
    assert (repository / '.git/index').read_bytes() == index
    assert git('status', '--porcelain') == ''
print('Installed diffofdiffs: version, patch, standalone HTML and Git-tree checks passed.')
