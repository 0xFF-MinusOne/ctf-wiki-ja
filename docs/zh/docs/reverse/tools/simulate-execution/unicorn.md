# Unicorn Engine

## Unicorn エンジンとは

Unicorn は、軽量でマルチプラットフォーム、マルチアーキテクチャの CPU エミュレータフレームワークです。マシンやデバイスの違いを無視して、CPU の動作に集中できます。たとえば、本物の CPU でそれらの操作を実行する必要はなく、コードの実行をエミュレートするだけでよい場合、マルウェアをより安全に解析してウイルスの特徴を検出したい場合、あるいはリバースエンジニアリングの過程であるコードの意味を検証したい場合などに応用できます。CPU エミュレータを使うと、こうした作業がとても便利になります。

Unicorn の特長(これは Unicorn が [qemu](http://www.qemu.org) をベースに開発されていることのおかげでもあります)は次のとおりです。

* 多くのアーキテクチャに対応: Arm, Arm64 (Armv8), M68K, Mips, Sparc, & X86 (X86_64 を含む)
* Windows と *nix 系 OS(Mac OSX, Linux, *BSD, Solaris を含むことを確認済み)にネイティブ対応
* プラットフォームに依存しない、簡潔で使いやすい API
* JIT コンパイル技術を使っており、性能が優れている

Unicorn エンジンの技術的な詳細は [Black Hat USA 2015](http://www.unicorn-engine.org/BHUSA2015-unicorn.pdf) で知ることができます。GitHub のプロジェクトページ: [unicorn](https://github.com/unicorn-engine/unicorn)

優れたツールですが、プログラム全体やシステム全体をエミュレートすることはできず、システムコールにも対応していません。メモリを手動でマップしてデータを書き込んでおく必要があり、その後で指定したアドレスからエミュレートを開始できます。

## 利用場面

Unicorn エンジンはどんなときに使えるでしょうか。

* マルウェアの中の興味深い関数を、有害なプロセスを作らずに呼び出せる
* CTF の競技で使う
* ファジングに使う
* gdb プラグイン、特にコードのエミュレート実行に基づくプラグインに使う
* 難読化されたコードをエミュレート実行する

## インストール方法

Unicorn を最も簡単にインストールする方法は pip を使うことで、コマンドラインで次のコマンドを実行するだけです(これは Python を好んで使うユーザー向けの方法です。C を使いたい場合は、公式サイトのドキュメントを見てソースパッケージをコンパイルする必要があります)。

``` shell
pip install unicorn
```

ソースコードからローカルでコンパイルしたい場合は、[ダウンロード](http://www.unicorn-engine.org/download/)ページからソースコードパッケージをダウンロードし、次のコマンドを実行します。

* *nix 系プラットフォームのユーザー

``` shell
$ cd bindings/python
$ sudo make install
```

* Windows プラットフォームのユーザー

``` shell
cd bindings/python
python setup.py install
```

Windows では、上記のコマンドを実行した後、[ダウンロード](http://www.unicorn-engine.org/download/)ページの `Windows core engine` のすべての dll ファイルを `C:\locationtopython\Lib\site-packages\unicorn` にコピーする必要もあります。

## Unicorn のクイックガイド

Python から unicorn の API を呼び出す方法と、それがいかに簡単にバイナリコードをエミュレートできるかを示します。ここで使う API はごく一部ですが、入門には十分です。

``` python
 1 from __future__ import print_function
 2 from unicorn import *
 3 from unicorn.x86_const import *
 4 
 5 # code to be emulated
 6 X86_CODE32 = b"\x41\x4a" # INC ecx; DEC edx
 7 
 8 # memory address where emulation starts
 9 ADDRESS = 0x1000000
10 
11 print("Emulate i386 code")
12 try:
13     # Initialize emulator in X86-32bit mode
14     mu = Uc(UC_ARCH_X86, UC_MODE_32)
15 
16     # map 2MB memory for this emulation
17     mu.mem_map(ADDRESS, 2 * 1024 * 1024)
18 
19     # write machine code to be emulated to memory
20     mu.mem_write(ADDRESS, X86_CODE32)
21 
22     # initialize machine registers
23     mu.reg_write(UC_X86_REG_ECX, 0x1234)
24     mu.reg_write(UC_X86_REG_EDX, 0x7890)
25 
26     # emulate code in infinite time & unlimited instructions
27     mu.emu_start(ADDRESS, ADDRESS + len(X86_CODE32))
28 
29     # now print out some registers
30     print("Emulation done. Below is the CPU context")
31 
32     r_ecx = mu.reg_read(UC_X86_REG_ECX)
33     r_edx = mu.reg_read(UC_X86_REG_EDX)
34     print(">>> ECX = 0x%x" %r_ecx)
35     print(">>> EDX = 0x%x" %r_edx)
36 
37 except UcError as e:
38     print("ERROR: %s" % e)
```

実行結果は次のとおりです。

``` shell
$ python test1.py 
Emulate i386 code
Emulation done. Below is the CPU context
>>> ECX = 0x1235
>>> EDX = 0x788f
```

サンプル中のコメントはすでにとても分かりやすいですが、それでも各行のコードについて説明します。

* 行番号2~3: Unicorn を使う前に `unicorn` モジュールをインポートします。サンプルでは x86 のレジスタ定数を使っているので、`unicorn.x86_const` モジュールもインポートする必要があります

* 行番号6: エミュレートしたいバイナリの機械語で、16進数で表されています。表すアセンブリ命令は "INC ecx" と "DEC edx" です

* 行番号9: 上記の命令をエミュレート実行する仮想アドレスです

* 行番号14: `Uc` クラスで Unicorn を初期化します。このクラスは2つの引数、ハードウェアアーキテクチャとハードウェアのビット数(モード)を受け取ります。サンプルでは x86 アーキテクチャの32ビットコードをエミュレート実行したいので、
戻り値を変数 `mu` で受け取ります

* 行番号17: `mem_map` メソッドで、行番号9で宣言したアドレスに、エミュレート実行用の 2MB のメモリ空間をマップします。プロセス中のすべての CPU 操作は、このメモリ領域だけにアクセスするはずです。マップされたメモリには、デフォルトで読み取り・書き込み・実行の権限があります

* 行番号20: エミュレート実行したいコードを、いまマップしたメモリに書き込みます。`mem_write` メソッドは2つの引数、書き込み先のメモリアドレスとメモリに書き込むコードを受け取ります

* 行番号23~24: `reg_write` メソッドで `ECX` と `EDX` レジスタの値を設定します

* 行番号27: `emu_start` メソッドでエミュレート実行を開始します。この API は4つの引数、エミュレート実行するコードのアドレス、エミュレート実行を停止するメモリアドレス(ここでは
`X86_CODE32` の最後の1バイトの位置)、エミュレート実行の時間、実行する命令数を受け取ります。サンプルのように後ろの2つの引数を省略すると、Unicorn はデフォルトで時間無制限・命令数無制限の条件でコードをエミュレート実行します

* 行番号32~35: `ECX` と `EDX` レジスタの値を出力します。レジスタの値の読み取りには関数 `reg_read` を使います


Python のサンプルをさらに見たい場合は、フォルダ [bindings/python](https://github.com/unicorn-engine/unicorn/tree/master/bindings/python) 以下のコードを参照してください。C のサンプルは、[sample](https://github.com/unicorn-engine/unicorn/tree/master/samples) フォルダ以下のコードを参照してください。


## 参考リンク

* [Unicorn Official Site](http://www.unicorn-engine.org/)
* [Quick tutorial on programming with Unicorn - with C & Python.](http://www.unicorn-engine.org/docs/)