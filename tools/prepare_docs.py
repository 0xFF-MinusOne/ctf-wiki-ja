#!/usr/bin/env python3
"""ビルド用の入力ディレクトリ .site-src/ を作る。

docs/zh/docs/ をコピーし、トップページ index.md を生成する。
元のファイルは変更しない。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "zh" / "docs"
DST = ROOT / ".site-src"

INDEX = """# CTF Wiki 日本語訳(Pwn・Reverse・Executable)

これは [CTF Wiki](https://ctf-wiki.org)([ctf-wiki/ctf-wiki](https://github.com/ctf-wiki/ctf-wiki))のうち、
**Pwn・Reverse・Executable** の部分を、簡体字中国語から日本語に翻訳したものです。
原文から翻訳(変更)しています。

- 原著: <https://github.com/ctf-wiki/ctf-wiki>(サイト: <https://ctf-wiki.org>)
- ライセンス: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.ja)(**非営利の目的でのみ利用できます**)
- この翻訳のリポジトリ: <https://github.com/0xff-minusone/ctf-wiki-ja>

## 目次

- [実行ファイル(Executable)](executable/elf/structure/basic-info.md)
- [Reverse](reverse/introduction.md)
- [Pwn](pwn/linux/user-mode/environment.md)

上部のタブ、または左のメニューから各章に移動できます。
"""

MATHJAX = """window.MathJax = {
  tex: { inlineMath: [["\\\\(", "\\\\)"]], displayMath: [["\\\\[", "\\\\]"]], processEscapes: true },
  options: { ignoreHtmlClass: ".*|", processHtmlClass: "arithmatex" }
};
"""


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    for sub in ("pwn", "reverse", "executable"):
        shutil.copytree(SRC / sub, DST / sub)
    (DST / "index.md").write_text(INDEX, encoding="utf-8")
    js = DST / "javascripts"
    js.mkdir()
    (js / "mathjax.js").write_text(MATHJAX, encoding="utf-8")
    print(f"prepared {DST}")


if __name__ == "__main__":
    main()
