#!/usr/bin/env python3
"""Pin readers must work with empty live siblings and reject moved checkouts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def repository(path, files):
    """Write a tiny Git fixture with immutable objects and a detached HEAD."""
    objects = path / '.git/objects'
    objects.mkdir(parents=True)
    (path / '.git/refs').mkdir()

    def object_id(kind, body):
        data = f'{kind} {len(body)}\0'.encode() + body
        sha = hashlib.sha1(data).hexdigest()
        dest = objects / sha[:2] / sha[2:]
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(zlib.compress(data))
        return sha

    tree = {}
    for name, body in files.items():
        dest = path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        entries = tree
        parts = Path(name).parts
        for part in parts[:-1]:
            entries = entries.setdefault(part, {})
        entries[parts[-1]] = body

    def write_tree(entries):
        rows = []
        for name, value in sorted(entries.items()):
            directory = isinstance(value, dict)
            sha = write_tree(value) if directory else object_id('blob', value)
            rows.append(f'{"40000" if directory else "100644"} {name}\0'.encode() + bytes.fromhex(sha))
        return object_id('tree', b''.join(rows))

    sha = object_id('commit', (f'tree {write_tree(tree)}\nauthor Fixture <fixture@example.org> 0 +0000\n'
                               'committer Fixture <fixture@example.org> 0 +0000\n\npin fixture\n').encode())
    (path / '.git/HEAD').write_text(sha + '\n')
    return sha


class PinPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.root = self.workspace / 'bennett-plugin'
        shutil.copytree(ROOT / 'tests', self.root / 'tests', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts')
        self.layout = self.workspace / 'layout'
        self.name = 'bennett-dialect-spec'
        spec = b'# accepted dialect fixture\n'
        bitcode = b'pinned bitcode fixture'
        files = {'SPEC_VERSIONS.toml': b'dialect="0.2.13"\nisa="0.8"\n',
                 'spec/Bennett-Dialect-Spec.md': spec,
                 'spec/bennett_markers.h': b'/* pinned header */\n',
                 'corpus/legality/results/raw/baseline.json': b'[{"id":"fixture"}]',
                 'scripts/native-check': b'published checker CLI fixture',
                 'scripts/native-check.cpp': b'published checker source fixture',
                 **{f'dist/llvm{m}/bennett-arith.bc': bitcode for m in (18, 23)},
                 **{f'dist/llvm{m}/bennett-runtimes.bc': bitcode for m in (18, 23)},
                 **{f'dist/llvm{m}/musl-sysroot/lib/native-support.bc': bitcode for m in (18, 23)},
                 **{f'dist/llvm{m}/manifest.json': b'{"fixture":true}' for m in (18, 23)}}
        sources = {name: f'/* published fixture {name} */'.encode()
                   for name in ('hashtable_marked.c', 'main_golden.c', 'hashtable.c')}
        files.update({f'ladder/rung-2/fixtures/{name}': body for name, body in sources.items()})
        files['ladder/rung-2/fixtures/sha256.json'] = json.dumps(
            {name: hashlib.sha256(body).hexdigest() for name, body in sources.items()}).encode()
        self.sha = repository(self.layout / self.name, files)
        self.names = (self.name, 'bennett-arith', 'bennett-isa-spec', 'bennett-runtimes',
                      'bennett-native-runtimes', 'bennett-vm', 'bennett-targets', 'bennett-conformance')
        for name in self.names:
            (self.workspace / name).mkdir()  # Live siblings deliberately have no files.
            if name != self.name:
                shutil.copytree(self.layout / self.name, self.layout / name)
            cache = self.root / f'.tmp/gate/cache/{name}@{self.sha[:12]}'
            cache.mkdir(parents=True)
            shutil.copytree(self.layout / name, cache / name)
        self.cache = self.root / f'.tmp/gate/cache/{self.name}@{self.sha[:12]}/{self.name}'
        (self.root / 'gate.toml').write_text('repo="bennett-plugin"\n' + ''.join(
            f'[siblings."{name}"]\nsha="{self.sha}"\n' for name in self.names))
        digest = hashlib.sha256(bitcode).hexdigest()
        (self.root / 'SPEC_VERSIONS.toml').write_text(
            f'dialect="0.2.13"\nisa="0.8"\ndialect_sha256="{hashlib.sha256(spec).hexdigest()}"\n'
            '[specs]\n"bennett-dialect-spec"="0.2.13"\n"bennett-isa-spec"="0.8"\n'
            f'[commits]\n"bennett-dialect-spec"="{self.sha}"\n[arith]\ncommit="{self.sha}"\n'
            + ''.join(f'llvm{m}_path="{self.workspace}/bennett-arith/dist/llvm{m}/bennett-arith.bc"\n'
                      f'llvm{m}_sha256="{digest}"\n' for m in (18, 23))
            + f'[native_comparison]\nruntime_commit="{self.sha}"\n'
            + ''.join(f'llvm{m}_support_sha256="{digest}"\n' for m in (18, 23))
            + f'checker_script_sha256="{hashlib.sha256(files["scripts/native-check"]).hexdigest()}"\n'
            + f'checker_source_sha256="{hashlib.sha256(files["scripts/native-check.cpp"]).hexdigest()}"\n')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('BENNETT_', 'GIT_'))}
        self.env['PYTHONPATH'] = str(self.root / 'tests')

    def run_python(self, code, success=True):
        result = subprocess.run([sys.executable, '-c', code], cwd=self.root, env=self.env,
                                capture_output=True, text=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_contract_ignores_empty_live_sibling_and_changed_registry(self):
        # Both the registry and text are read with git show at the gate pin.
        (self.cache / 'SPEC_VERSIONS.toml').write_text('dialect="0.2.14"\n')
        (self.cache / 'spec/Bennett-Dialect-Spec.md').write_text('unaccepted draft\n')
        self.run_python('import contracts; assert not contracts.drift()')

    def test_contract_rejects_stale_versions_commits_and_bytes(self):
        metadata = self.root / 'SPEC_VERSIONS.toml'
        original = metadata.read_text()
        for old, new in (('0.2.13', '0.2.14'), ('0.8', '999'), (self.sha, 'f' * 40),
                         (hashlib.sha256(b'# accepted dialect fixture\n').hexdigest(), 'f' * 64)):
            with self.subTest(field=old):
                metadata.write_text(original.replace(old, new))
                self.run_python('import contracts; assert contracts.drift()')
        metadata.write_text(original)
        self.run_python('import contracts; from unittest.mock import patch; '
                        'text = contracts.dialect_text(); '
                        'contracts.dialect_text = lambda: text + "corrupt"; assert contracts.drift()')

    def test_corrupt_pinned_arithmetic_is_rejected_on_both_majors(self):
        for major in (18, 23):
            with self.subTest(major=major):
                path = (self.root / f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}/bennett-arith'
                        / f'dist/llvm{major}/bennett-arith.bc')
                path.write_bytes(b'corrupt pinned publication')
                result = self.run_python(f'from contracts import arith_path; arith_path({major})', False)
                self.assertIn(f'LLVM {major}: arith pin mismatch', result.stderr)

    def test_arith_ignores_live_and_legacy_override_paths(self):
        self.env['BENNETT_SIBLINGS'] = str(self.workspace)
        self.env['BENNETT_ARITH_PINNED_ROOT'] = str(self.workspace / 'bennett-arith/dist')
        result = self.run_python('from contracts import arith_path, arith_manifest; '
                                 'print(arith_path(18)); assert arith_manifest(18)["fixture"]')
        self.assertIn(f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}', result.stdout)

    def test_gate_layout_precedes_cache(self):
        self.env['BENNETT_GATE_LAYOUT'] = str(self.layout)
        result = self.run_python('from pinned_siblings import sibling; print(sibling("bennett-dialect-spec"))')
        self.assertEqual(result.stdout.strip(), str(self.layout / self.name))

    def test_interpreter_readers_ignore_empty_live_siblings(self):
        self.env['BENNETT_SIBLINGS'] = str(self.workspace)
        self.run_python('import scalars, production, review_regressions; '
                        'from pinned_siblings import sibling; '
                        'expected = sibling("bennett-isa-spec") / "reference-interpreter/target/debug/bennett-isa-ref"; '
                        'assert scalars.REF == production.REF == review_regressions.REF == expected')

    def test_native_library_ignores_live_override(self):
        self.env['BENNETT_VM_NATIVE_LIBRARY'] = str(self.workspace / 'bennett-vm/live.so')
        self.run_python('from native_comparison import vm_library; from pinned_siblings import sibling; '
                        'assert vm_library() == sibling("bennett-vm") / "target/release/libbennett_vm.so"')

    def test_native_support_ignores_live_override(self):
        self.env['BENNETT_NATIVE_SUPPORT_PINNED_ROOT'] = str(self.workspace / 'bennett-runtimes/dist')
        self.run_python('from native_link import support; from pinned_siblings import sibling; '
                        'assert support(18) == sibling("bennett-native-runtimes") / '
                        '"dist/llvm18/musl-sysroot/lib/native-support.bc"')

    def test_runtime_and_conformance_inputs_ignore_live_overrides(self):
        self.env['BENNETT_ALLOCATOR_PINNED_ROOT'] = str(self.workspace / 'bennett-runtimes/dist')
        self.env['BENNETT_NATIVE_TOOL_ROOT'] = str(self.workspace / 'bennett-runtimes')
        # Stop at the first command that consumes each resolved publication.
        self.run_python('''
import hashlib, sys
from unittest.mock import patch
from types import SimpleNamespace
import allocator_closure, native_hello, native_fixtures, native_checked
from pinned_siblings import sibling
runtime = sibling('bennett-runtimes') / 'dist/llvm18/bennett-runtimes.bc'
allocator_closure.RUNTIME_SHA[18] = hashlib.sha256(runtime.read_bytes()).hexdigest()
expected = {
    native_hello: runtime.parent / 'musl-sysroot/include',
    native_fixtures: sibling('bennett-conformance') / 'ladder/rung-2/fixtures/hashtable.c',
    native_checked: runtime,
}
class PublicationReached(Exception): pass
for module, path in expected.items():
    reached = []
    def stop(command):
        if path in command:
            reached.append(path)
            raise PublicationReached()
        return SimpleNamespace(stdout='')
    with patch.object(sys, 'argv', [module.__name__, '--major', '18']), patch.object(module, 'run', stop):
        try: module.main()
        except PublicationReached: pass
    assert reached == [path], (module.__name__, reached)
''')

    def test_corpus_archive_ignores_empty_live_sibling(self):
        self.env['BENNETT_SIBLINGS'] = str(self.workspace)
        self.run_python('from corpus_gate import bootstrap; '
                        'assert bootstrap() == {"fixture": {"id": "fixture"}}')

    def test_verification_script_uses_pinned_interpreter(self):
        self.env['BENNETT_SIBLINGS'] = str(self.workspace)
        self.run_python('import runpy; from pinned_siblings import ROOT, sibling; '
                        'script = runpy.run_path(str(ROOT / "scripts/record-verification.py")); '
                        'assert script["ISA_REF"] == sibling("bennett-isa-spec") / '
                        '"reference-interpreter/target/debug/bennett-isa-ref"')

    def test_build_uses_pinned_arithmetic_paths(self):
        # Probe the actual llvm-config fallback flags without compiling the plugin.
        shim = self.workspace / 'bin'
        shim.mkdir()
        (shim / 'python3').symlink_to(sys.executable)
        (shim / 'git').symlink_to(shutil.which('git'))
        compiler = shim / 'g++'
        compiler.write_text('#!' + sys.executable + '\nimport sys\nprint(repr(sys.argv), flush=True)\nsys.exit(99)\n')
        compiler.chmod(0o755)
        (self.root / 'src').mkdir()
        (self.root / 'src/Bennett.h').write_text('')
        (self.root / 'src/Unit.cpp').write_text('')
        self.env['PATH'] = str(shim)
        result = subprocess.run([sys.executable, self.root / 'scripts/build'], cwd=self.root,
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}', result.stdout)
        self.assertNotIn(f'{self.workspace}/bennett-arith/dist', result.stdout)

    def configure_cmake(self, major, label):
        if not (self.root / 'CMakeLists.txt').exists():
            shutil.copy2(ROOT / 'CMakeLists.txt', self.root / 'CMakeLists.txt')
            shutil.copytree(ROOT / 'src', self.root / 'src')
            metadata = self.root / 'SPEC_VERSIONS.toml'
            text = metadata.read_text()
            for m in (18, 23):
                text = text.replace(f'llvm{m}_path="{self.workspace}/bennett-arith',
                                    f'llvm{m}_path = ".tmp/gate/cache/bennett-arith@{self.sha[:12]}/bennett-arith')
                text = text.replace(f'llvm{m}_sha256=', f'llvm{m}_sha256 = ')
            metadata.write_text(text)
        build = self.root / f'build/{label}-{major}'
        result = subprocess.run(['cmake', '-S', self.root, '-B', build,
                                 f'-DLLVM_DIR=/usr/lib/llvm-{major}/lib/cmake/llvm',
                                 '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'],
                                cwd=self.workspace, env=self.env, capture_output=True,
                                text=True, timeout=30)
        return result, build

    def test_cmake_uses_absolute_pinned_arithmetic_paths(self):
        for layout in (False, True):
            if layout:
                self.env['BENNETT_GATE_LAYOUT'] = str(self.layout)
            for major in (18, 23):
                with self.subTest(layout=layout, major=major):
                    result, build = self.configure_cmake(major, f'layout-{layout}')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    checkout = (self.layout / 'bennett-arith' if layout else self.root /
                                f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}/bennett-arith')
                    path = checkout / f'dist/llvm{major}/bennett-arith.bc'
                    commands = json.loads((build / 'compile_commands.json').read_text())
                    for command in commands:
                        self.assertIn(str(path), command['command'])

    def test_cmake_rejects_missing_pinned_arithmetic(self):
        for major in (18, 23):
            with self.subTest(major=major):
                missing = (self.root / f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}'
                           / f'bennett-arith/dist/llvm{major}/bennett-arith.bc')
                missing.unlink()
                result, _ = self.configure_cmake(major, 'missing')
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(str(missing), result.stderr)

    def test_missing_cache_has_one_actionable_message(self):
        shutil.rmtree(self.cache)
        result = self.run_python('from pinned_siblings import sibling; sibling("bennett-dialect-spec")', False)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        for fragment in (self.name, self.sha, 'live ../bennett-dialect-spec HEAD=unavailable',
                         'gate_run.py verify --repo bennett-plugin --sha HEAD'):
            self.assertIn(fragment, result.stderr)

    def test_missing_cache_reports_actual_live_head(self):
        live_sha = repository(self.workspace / self.name, {'live.txt': b'unaccepted live sibling'})
        shutil.rmtree(self.cache)
        result = self.run_python('from pinned_siblings import sibling; sibling("bennett-dialect-spec")', False)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn(f'live ../{self.name} HEAD={live_sha}', result.stderr)

    def test_moved_cache_is_rejected(self):
        (self.cache / '.git/HEAD').write_text('f' * 40 + '\n')
        result = self.run_python('from pinned_siblings import sibling; sibling("bennett-dialect-spec")', False)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn('f' * 40, result.stderr)

    def test_gate_preflight_stops_after_one_pin_error(self):
        shutil.rmtree(self.root / f'.tmp/gate/cache/bennett-arith@{self.sha[:12]}/bennett-arith')
        build = self.root / 'scripts/build'
        build.write_text('#!/bin/sh\necho "build must not run after missing pin"\nexit 99\n')
        result = subprocess.run(['bash', self.root / 'scripts/gate'], cwd=self.root, env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn('bennett-arith pinned ' + self.sha, result.stderr)

    def test_moved_checkout_fails_without_falling_back(self):
        self.env['BENNETT_GATE_LAYOUT'] = str(self.layout)
        (self.layout / self.name / '.git/HEAD').write_text('f' * 40 + '\n')
        result = self.run_python('from pinned_siblings import sibling; sibling("bennett-dialect-spec")', False)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn(self.sha, result.stderr)
        self.assertIn('f' * 40, result.stderr)

    def test_missing_gate_checkout_does_not_fall_back_to_cache(self):
        self.env['BENNETT_GATE_LAYOUT'] = str(self.layout)
        shutil.rmtree(self.layout / self.name)
        result = self.run_python('from pinned_siblings import sibling; sibling("bennett-dialect-spec")', False)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn(self.sha, result.stderr)


if __name__ == '__main__':
    unittest.main()
