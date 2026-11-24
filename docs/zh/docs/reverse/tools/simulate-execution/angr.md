# angr 

## Introduction

[angr](https://github.com/angr/angr) は Python で書かれたクロスプラットフォームのオープンソースのバイナリ**混合**(Concolic、すなわち concrete + symbolic)実行エンジンで、実用的なバイナリ解析ツール群を提供します。angr の詳しい紹介は [公式サイト](https://angr.io) を、angr が提供する API は[ドキュメント](https://api.angr.io/)を参照してください。

CTF のリバースエンジニアリング問題では、angr の強力な混合実行エンジンによって自動化した解析をうまく進められ、解答にかかる時間を大幅に節約できます。

## インストール

angr 本体は pip で直接インストールできます。

```shell
$ pip3 install angr
```

[angr-management](https://github.com/angr/angr-management) は angr のグラフィカルなインターフェースです。インストール後、ターミナルで `angr-management` と入力するとそのまま起動できます。

```shell
$ pip3 install angr-management
```

[angrop](https://github.com/angr/angrop) も angr の開発チームのプロジェクトで、ROP gadget の自動収集と ROP chain の構築ができます。

```shell
$ pip3 install angrop
```

## 基本的な使い方

この節では、angr の基本的な使い方と、angr でよく使う API について説明します。

> 注: [angr_ctf](https://github.com/jakespringer/angr_ctf) は angr の入門者向けの非常によい練習用プロジェクトで、これを通じて angr の基本的な使い方に慣れることができます。

### Project

angr でバイナリファイルを解析するには、最初のステップとして `angr.Project` クラスを作成します。以降のすべての操作は、このクラスのインスタンスを基に進めます。例を示します。

```python
>>> import angr
>>> bin_path = './test' # file to be analyzed
>>> proj = angr.Project(bin_path)
WARNING | 2022-11-23 19:25:30,006 | cle.loader | The main binary is a position-independent executable. It is being loaded with a base address of 0x400000.
```

まず、project から対応するバイナリファイルの基本情報を取得できます。

```python
>>> proj.arch     # architecture of the binary file
<Arch AMD64 (LE)>
>>> hex(proj.entry)    # entry point of the binary file
'0x401060'
>>> proj.filename # name of the binary file
'./test'
```

- `arch` は `archiinfo.Arch` クラスのインスタンスで、このファイルを実行する CPU の情報など、さまざまなデータを含みます。

  - `arch.bits` & `arch.bytes`: CPU のワード長(単位はビット/バイト)。

  - `arch.name`: アーキテクチャ名。例えば _X86_ 。

  - `arch.memory_endness`: エンディアン。ビッグエンディアンは `Endness.BE`、リトルエンディアンは `Endness.LE`。

    > ソースコードにはもう1つ「ミドルエンディアン」`Endness.ME` もあります :)

#### factory - 便利なクラスのファクトリ

`project.factory` は、便利なクラスのコンストラクタをいくつか提供します。

##### block - 基本ブロック

angr は基本ブロック単位でコードを解析します。`project.factory.block(address)` で、指定したアドレスが属する**基本ブロック**(`Block` クラスのインスタンス)を取得できます。

```python
>>> block = proj.factory.block(proj.entry) # extract the basic block
>>> block.pp() # pretty-print of disassemble code of the block
        _start:
401060  endbr64
401064  xor     ebp, ebp
401066  mov     r9, rdx
401069  pop     rsi
40106a  mov     rdx, rsp
40106d  and     rsp, 0xfffffffffffffff0
401071  push    rax
401072  push    rsp
401073  lea     r8, [__libc_csu_fini]
40107a  lea     rcx, [__libc_csu_init]
401081  lea     rdi, [main]
401088  call    qword ptr [0x403fe0]
>>> block.instructions # instructions in the block
12
>>> block.instruction_addrs # addr of each instruction
(4198496, 4198500, 4198502, 4198505, 4198506, 4198509, 4198513, 4198514, 4198515, 4198522, 4198529, 4198536)
```

##### state - エミュレート実行の状態

angr は `SimState` クラスで _シミュレートされたプログラムの状態_(simulated program state)を表します。私たちが行うさまざまな操作は、実際にはある state から別の state へ進める過程です。

`project.factory.entry_state()` でプログラムの初期実行状態を取得し、`project.factory.blank_state(addr)` でプログラムを指定したアドレスから実行する空白の状態を取得します。

```python
>>> state = proj.factory.entry_state()
>>> state = proj.factory.blank_state(0xdeadbeef)
```

- `state.regs`: レジスタ状態のグループ。各レジスタは _ビットベクタ_(BitVector)で、レジスタ名で対応するレジスタにアクセスできます(例: `state.regs.esp -= 12`)。
- `state.mem`: この状態のメモリアクセス用インターフェース。`state.mem[addr].type` で直接メモリにアクセスできます(例: `state.mem[0x1000].long = 4`。読み取りの場合は、ビットベクタか実際の値かを表す `.resolved` または `.concrete` も指定する必要があります。例: `state.mem[0x1000].long.concrete`)。
- `state.memory`: 別の形式のメモリアクセス用インターフェース。
  - `state.memory.load(addr, size_in_bytes)`: そのアドレスにある、指定したサイズのビットベクタを取得する。
  - `state.memory.store(addr, bitvector)`: ビットベクタを指定したアドレスに格納する。
- `state.posix`: POSIX 関連の環境インターフェース。例えば `state.posix.dumps(fileno)` で、対応するファイルディスクリプタ上のストリームを取得する。

エミュレート実行状態の情報を取得するこれらのインターフェースのほかに、求解のためのインターフェース `state.solver` もあります。これについては後の節で説明します。

##### simulation\_manager - エミュレート実行器

angr は、状態の実行方法を `SimulationManager` クラスとして独立させています。次の2つの書き方は等価です。

```python
>>> proj.factory.simgr(state)
<SimulationManager with 1 active>
>>> proj.factory.simulation_manager(state)
<SimulationManager with 1 active>
```

重要なメソッドは次の2つです。

- `simgr.step()`: **基本ブロック単位**のステップ実行。
- `simgr.explore()`: パス探索を行い、条件を満たす状態を見つける。

`simgr.explore()` のデフォルトの引数は `find`、つまり**期待する条件**です。エミュレート実行器がパス探索の途中で、現在の状態がこの条件を満たすと見つけると、その状態は `simgr.found` リストに入れられます。見つからなければ、このリストは空になります。

期待する条件は、通常はあるアドレスまで実行が到達することにできます。

```python
>>> simgr.explore(find=0x80492F0) # explore to a specific address
WARNING  | 2023-07-17 04:04:28,825 | angr.storage.memory_mixins.default_filler_mixin | The program is accessing memory with an unspecified value. This could indicate unwanted behavior.
WARNING  | 2023-07-17 04:04:28,825 | angr.storage.memory_mixins.default_filler_mixin | angr will cope with this by generating an unconstrained symbolic variable and continuing. You can resolve this by:
WARNING  | 2023-07-17 04:04:28,826 | angr.storage.memory_mixins.default_filler_mixin | 1) setting a value to the initial state
WARNING  | 2023-07-17 04:04:28,826 | angr.storage.memory_mixins.default_filler_mixin | 2) adding the state option ZERO_FILL_UNCONSTRAINED_{MEMORY,REGISTERS}, to make unknown regions hold null
WARNING  | 2023-07-17 04:04:28,826 | angr.storage.memory_mixins.default_filler_mixin | 3) adding the state option SYMBOL_FILL_UNCONSTRAINED_{MEMORY,REGISTERS}, to suppress these messages.
WARNING  | 2023-07-17 04:04:28,826 | angr.storage.memory_mixins.default_filler_mixin | Filling memory at 0x7ffeff60 with 4 unconstrained bytes referenced from 0x819af30 (strcmp+0x0 in libc.so.6 (0x9af30))
WARNING  | 2023-07-17 04:04:28,826 | angr.storage.memory_mixins.default_filler_mixin | Filling memory at 0x7ffeff70 with 12 unconstrained bytes referenced from 0x819af30 (strcmp+0x0 in libc.so.6 (0x9af30))
<SimulationManager with 1 active, 16 deadended, 1 found>
```

期待する条件は、_状態_ を引数に取る、独自のブール関数にすることもできます。例えば、指定した文字列を出力するパスを探したい場合は、その文字列が出力に含まれているかどうかを判定する方法を選べます。`state.posix.dumps(ファイルディスクリプタ)` で、対応するファイルディスクリプタ上の文字ストリームを取得できます。

```
>>> def foo(state):
...     return b"Good" in state.posix.dumps(1)
... 
>>> simgr.explore(find=foo)
<SimulationManager with 17 deadended, 1 found>

```

`find` 引数のほかに、`avoid` 引数も指定できます。これはエミュレータの実行中に**避けるべき**条件で、状態がこの条件に合致すると `.avoided` リストに入れられ、それ以上実行されません。同様に、`avoid` 引数もアドレスか、独自のブール関数にできます。

このほか、`num_find` 引数で、探したい条件を満たす状態の数を指定できます。指定しない場合は、条件を満たすすべての状態が `.found` リストに格納されます。

### Claripy

`Claripy` は angr の**求解エンジン**(solver engine)で、内部ではいくつかのバックエンド(concrete bitvectors、SAT solvers など)をシームレスに混合して使います。私たちが直接やり取りする必要は通常ありませんが、提供されるインターフェースはよく使います。

#### bitvector - ビットベクタ

**ビットベクタ**(bitvector)は angr の求解エンジンの重要な要素で、**ビットの並び**(a sequence of bits)を表します。

`claripy.BVV(int_value, size_in_bits)` または `claripy.BVV(string_value)` で、具体値(concrete value)を持つ、指定した長さのビットベクタ値(bitvector value)を作成できます。

```python
>>> bvv = claripy.BVV(b'arttnba3')
>>> bvv
<BV64 0x617274746e626133>
>>> bvv2 = claripy.BVV(0xdeadbeef, 32)
>>> bvv2
<BV32 0xdeadbeef>
```

同じ長さのビットベクタ同士は演算できます。長さの異なるビットベクタは、`.zero_extend(extended_bits)` でビット拡張(0埋め)してから演算できます。ビットベクタの値の演算でも、同様にオーバーフローが起こることに注意してください。

```python
>>> bvv2 = bvv2.zero_extend(32)
>>> bvv + bvv2
<BV64 0x617274754d102022>
>>> bvv * bvv
<BV64 0x9842ff8e63f3b029>
```

ビットベクタには、具体値(concrete value)を表す `bitvector value` のほかに、**シンボル変数**(symbolic variable)を表す `bitvector symbol` があります。`claripy.BVS(name, size_in_bits)` で、名前付きで指定した長さのビットベクタシンボル(bitvector symbol)を作成できます。

```python
>>> bvs = claripy.BVS("x", 64)
>>> bvs
<BV64 x_0_64>
>>> bvs2 = claripy.BVS("y", 64)
>>> bvs2
<BV64 y_1_64>
```

ビットベクタシンボルとビットベクタ値の間でも同様に演算でき、より複雑な式を組み立てられます。

```python
>>> bvs3 = (bvs * bvs2 + bvv) / bvs
>>> bvs3
<BV64 (x_0_64 * y_1_64 + 0x617274746e626133) / x_0_64>
```

`.op` と `.args` で、ビットベクタの演算の種類と引数を取得できます。

```python
>>> bvv.op
'BVV'
>>> bvs.op
'BVS'
>>> bvs3.op
'__floordiv__'
>>> bvs3.args
(<BV64 x_0_64 * y_1_64 + 0x617274746e626133>, <BV64 x_0_64>)
>>> bvv.args
(7021802812440994099, 64)
```

#### state - エミュレート実行の状態

##### 状態の求解

前に述べたとおり、`state.solver` は状態に基づく求解用のインターフェースを提供しています。例えば solver にも、ビットベクタを作成する `.BVV()` と `.BVS()` があります。

ビットベクタシンボルの具体値を求めたいときは、まずビットベクタシンボルを状態のメモリ/レジスタに格納し、simgr で目的の状態まで探索した後、`state.solver.eval()` メンバ関数で、対応するビットベクタの現在の状態での値を取得できます。簡単な例を示します。

```python
bvs_to_solve = claripy.BVS('bvs_to_solve', 64)
init_state = proj.factory.entry_state()
init_state.memory.store(0xdeadbeef, bvs_to_solve)
simgr = proj.factory.simgr(init_state)
simgr.explore(find = 0xbeefdead)

solver_state = simgr.found[0]
print(solver_state.solver.eval(bvs_to_solve))
```

##### メモリ操作

前に述べたとおり、状態のメモリは `state.memory` の対応するインターフェースで操作できます。

- `state.memory.load(addr, size_in_bytes)`: そのアドレスにある、指定したサイズのビットベクタを取得する
- `state.memory.store(addr, bitvector)`: ビットベクタを指定したアドレスに格納する

具体値を格納する場合は、`endness` 引数でエンディアンを指定する必要があることに注意してください。

### Emulated Filesystem

angr では、ファイルシステムに対する操作は `SimFile` オブジェクトで行います。SimFile は _ストレージ_ の抽象モデルで、1つの SimFile オブジェクトは一連のバイトやシンボルなどを表せます。

`angr.SimFile()` でシミュレートされたファイルを作成できます。具体値とシンボル変数を持つ SimFile を作成する例は次のとおりです。

```python
>>> import angr, claripy
>>> sim_file = angr.SimFile('a_file', content = "flag{F4k3_f1@9!}\n")
>>> bvs = claripy.BVS('bvs', 64)
>>> sim_file2 = angr.SimFile('another_file', bvs, size=8) # size in bytes there
```

シミュレートされたファイルは、特定の状態と関連付ける必要があります。`state.fs.insert(sim_file)` または `sim_file.set_state(state)` で、SimFile を状態のファイルシステムに挿入できます。

```python
>>> state.fs.insert('test_file', sim_file)
```

ファイルから内容を読み取ることもできます。

```python
>>> pos = 0
>>> data, actural_read, pos = sim_file.read(pos, 0x100)
```

_ストリーム_(Streams。例えば標準 IO や TCP 接続など)型のファイルは、`angr.SimPackets()` で作成できます。

```python
>>> sim_packet = angr.SimPackets('my_packet')
>>> sim_packet
<angr.storage.file.SimPackets object at 0x7f75626a2e80>
```

### Constraints

前に、ビットベクタ同士で演算できると述べました。同様に、ビットベクタ同士で**比較演算**もでき、その結果は `Bool` 型のオブジェクトになります。

```python
>>> bvv = claripy.BVV(0xdeadbeef, 32)
>>> bvv2 = claripy.BVV(0xdeadbeef, 32)
>>> bvv == bvv2
<Bool True>
>>> bvs = claripy.BVS('bvs', 32)
>>> bvs == bvv + bvv2
<Bool bvs_0_32 == 0xbd5b7dde>
>>> bvs2 = claripy.BVS('bvs2', 32)
>>> bvs2 > bvs * bvv + bvv2
<Bool bvs2_1_32 > bvs_0_32 * 0xdeadbeef + 0xdeadbeef>
```

シンボル値を含む比較では、`Bool` 型のオブジェクトが対応する式をそのまま表します。そのため**制約条件**として状態に追加でき、`state.solver.add()` で対応する状態に制約を追加できます。

```python
>>> state.solver.add(bvs == bvv + bvv2)
>>> state.solver.add(bvs2 > bvs * bvv + bvv2)
>>> state.solver.eval(bvs2) # get the concrete value under constraints
```

Bool クラスのほかに、Claripy にはビットベクタを結果とする演算操作もいくつかあります。例を示します(全体は[ドキュメント](https://docs.angr.io/advanced-topics/claripy)を読んでください)。

```python
>>> claripy.If(bvs == bvs2, bvs, bvs2)
<BV32 if bvs_0_32 == bvs2_1_32 then bvs_0_32 else bvs2_1_32>
```

### Function hook

ある関数を hook したいことがあります。そのときは `project.hook(addr = call_insn_addr, hook = my_function, length = n)` で、対応する call 命令を hook できます。

- `call_insn_addr`: hook する call 命令のアドレス
- `my_function`: 自作の Python 関数
- `length`: call 命令の長さ

自作の関数は、`state` を引数に取る関数にします。angr は decorator のシンタックスシュガーも提供しているので、次の2つの書き方のどちらでもかまいません。

```python
# method 1
@project.hook(0x1234, length=5)
def my_hook_func(state):
    # do something, this is an example
    state.regs.eax = 0xdeadbeef

# method 2
def my_hook_func2(state):
    # do something, this is an example
    state.regs.eax = 0xdeadbeef
proj.hook(addr = 0x5678, hook = my_hook_func2, length = 5)
```

### Simulated Procedure

angr では、`angr.SimProcedure` クラスで**ある状態上での1つの実行過程**を表します。つまり、関数は実際には SimPrecedure です。

`angr.SimProcedure` を継承するクラスを作り、`run()` メソッドをオーバーライドすることで、独自の関数を表せます。`run()` メソッドの引数は、その関数が受け取る引数です。

```python
class MyProcedure(angr.SimProcedure):
    def run(self, arg1, arg2):
        # do something, this's an example
        return self.state.memory.load(arg1, arg2)
```

独自の関数過程は、主にファイル中の既存の関数を置き換えるために使います。例えば angr は、デフォルトで組み込みの SimProcedure をいくつか使って、一部のライブラリ関数を置き換えます。

そのバイナリファイルのシンボルテーブルがすでにある場合は、`project.hook_symbol(symbol_str, sim_procedure_instance)` で、ファイル中の対応するシンボルをすべて自動で hook できます。このとき `run()` メソッドの**引数は、置き換えられる関数が受け取る引数**です。例を示します。

```python3
import angr
import claripy

class MyProcedure(angr.SimProcedure):
    def run(self, arg1, arg2):
        # do something, this's an example
        return self.state.memory.load(arg1, arg2)

proj = angr.Project('./test')
proj.hook_symbol('func_to_hook', MyProcedure())
```

もちろん、SimProcedure の `run()` の中では、便利なメンバ関数もいくつか使えます。

- `ret(expr)`: 関数から戻る。
- `jump(addr)`: 指定したアドレスにジャンプする。
- `exit(code)`: プログラムを終了する。
- `call(addr, args, continue_at)`: ファイル中の関数を呼び出す。
- `inline_call(procedure, *args)`: 別の SimProcedure をインラインで呼び出す。

### stash

angr では、異なる状態は simulation manager の異なる stash に整理されており、必要に応じてステップ実行、フィルタ、マージ、移動などを行えます。

#### stash の種類

angr には次の種類の stash があります。

- `simgr.active`: アクティブな状態のリスト。代替が指定されていなければ、エミュレータがデフォルトで実行する
- `simgr.deadended`: 終了した状態のリスト。状態がそれ以上実行を続けられなくなったとき(例えば有効な命令がない、命令ポインタが無効、すべての後続(successors)を満たさない場合)に、このリストに入れられる
- `simgr.pruned`: 枝刈りされた状態のリスト。`LAZY_SOLVES` が指定されている場合、状態は必要なときにだけ充足可能性を検査します。`LAZY_SOLVES` の指定下である状態が充足不可能(unsat)だと分かると、状態の階層(state hierarchy)をたどって、履歴の中で最初に充足不可能になった時点を確認し、その時点とそのすべての子孫が _枝刈り_(pruned)されてこのリストに入れられる
- `simgr.unconstrained`: 制約のない状態のリスト。`SimulationManager` の作成時に `save_unconstrained=True` を指定すると、**制約のない**(unconstrained、すなわち命令ポインタがユーザーデータやその他の出所のシンボル化されたデータに制御されている)状態と見なされたものがこのリストに入れられる
- `simgr.unsat`: 充足不可能な状態のリスト。`SimulationManager` の作成時に `save_unsat=True` を指定すると、充足不可能(unsatisfiable、すなわち**制約の矛盾**がある状態。例えば同時に入力が `"AAAA"` でもあり `"BBBB"` でもあることを要求する場合)と見なされた状態がこのリストに入れられる

stash ではない状態のリストとして `errored` もあります。実行中にエラーが発生すると、状態とそのエラーが `ErrorRecord` インスタンスに包まれ(`record.state` と `record.error` でアクセスできます)、その record が `errored` に挿入されます。`record.debug()` でデバッグウィンドウを起動できます

#### stash の操作

`stash.move()` で、stash の間で状態を移動できます。使い方は次のとおりです。

```python
>>> simgr.move(from_stash = 'unconstrained', to_stash = 'active')
```

移動の際に、`filter_func` 引数を指定してフィルタすることもできます。

```python
>>> def filter_func(state):
...     return b'arttnba3' in state.posix.dumps(1)
...
>>> simgr.move(from_stash = 'unconstrained', to_stash = 'active', filter_func = filter_func)
```

stash は本質的には list なので、初期化時に辞書の形で各 stash の初期内容を指定できます。

```python
>>> simgr = proj.factory.simgr(init_state,
...     stashes = {
...             'active':[init_state],
...             'found':[],
...     })
```

## 参考

[Github - angr](https://github.com/angr/angr)

[angr documentation](https://api.angr.io/)

[【ANGR.0x00】angr-CTF から入門する angr の基本的な使い方](https://arttnba3.cn/2022/11/24/ANGR-0X00-ANGR_CTF/)

