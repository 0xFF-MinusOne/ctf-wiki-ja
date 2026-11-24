# V8 Design History

この節では V8 の発展の歴史をおおまかに紹介します。発展的な読み物として参考にしてください。

### 2008: Full-code Generation + Semi-optimization

この時期の V8 は公開されたばかりで、簡単に言うと全コード生成の方式を使っていました。**すべての JS コードを JIT コンパイルして対応するアーキテクチャのマシンコードを生成し**、そのうえでごく一部の最適化を行います。

![](https://s2.loli.net/2025/03/11/LeisDWScb2ZVUC1.png)

### 2010: Full-code Generation + Crankshaft JIT Compiler & Optimizer

2 年ほど手直しを重ねた後、V8 の開発チームは既存のコード最適化部分を切り出して、独立した JIT compiler としました。これが [Crankshaft](https://blog.chromium.org/2010/12/new-crankshaft-for-v8.html) で、JS コードのコンパイルパイプラインにも Crankshaft への分岐が加わりました。同時に V8 は Deoptimization の仕組みも導入し始めました。

![](https://s2.loli.net/2025/03/11/cd1xWp8gA5wnyhD.png)

> JS コードから生成された AST を、既存の全コードコンパイルエンジンに渡すのはいつか、Crankshaft に渡すのはいつか。これは主に chromium が有効にしている設定オプションで決まります。この時期の chromium の動作モードは、JS をまず既存の全コード生成エンジンに渡してから Crankshaft で最適化させる方式でも、直接 Crankshaft に渡す方式でもかまいませんでした。

### 2014: Full-code Generation + Crankshaft / TurboFan JIT Compiler & Optimizer

さらに 4 年が経ち、[TurboFan](https://v8.dev/docs/turbofan) という新しい JavaScript JIT Compiler + Optimizer が登場しました。このときのコンパイルパイプラインは次のようになり、既存のパイプラインから TurboFan へ向かう経路が追加で分岐し、TurboFan と Crankshaft が並行して存在していました。

![](https://s2.loli.net/2025/03/11/7Ptx93koOHsIi12.png)

> JS コードから生成された AST を、既存の全コードコンパイルエンジンに渡すのはいつか、Crankshaft に渡すのはいつか、TurboFan に渡すのはいつか。前と同様に、これも具体的な設定オプションで決まります。

### 2016: Ignition Interpreter + Full-code Generation + Crankshaft / TurboFan JIT Compiler & Optimizer

さらに 2 年が経ち、[Ignition](https://v8.dev/blog/ignition-interpreter) という JS インタプリタが登場しました。V8 engine は**初めてインタプリタ実行という概念を導入**しました。理由は、全コード生成は依然として時間も空間も消費しすぎ、実行効率も悪かったためです。強力な TurboFan の支援があっても、直接インタプリタで実行するほうが速く、この年から、インタプリタ実行が V8 が JS コードを実行する主な方法になりました。

![](https://s2.loli.net/2025/03/11/CocnM4vmT8qpXwx.png)

Ignition はこの時点では_オプション機能_でした。Ignition を有効にした V8 では、JS AST が Ignition に渡されて bytecode が生成された後にインタプリタ実行されます。よく実行される bytecode は TurboFan に渡されて JIT コンパイルされ、マシンコードが生成されるか、あるいは従来の全コード生成 + Crankshaft による最適化の経路に渡されます。一方、Ignition を有効にしていない V8 は、従来の全コード生成 + Crankshaft による最適化の経路を通ります(2010 年に逆戻りしたようなものです)。

> この時点でコンパイルパイプライン全体は大きく複雑になり、新たなアーキテクチャの最適化が必要になるのは必然でした――

### 2017: Ignition Interpreter + TurboFan JIT Compiler

さらに 1 年が経ち、Ignition と TurboFan というこの 2 つの強力な存在ができたことで、_全コード生成の JIT Compiler と古い Crankshaft は存在する必要がなさそうだ_ということになり、この 2 つのコンポーネントは直接削除されました。**コンパイルパイプラインは、すっきりした Ignition Interpreter + TurboFan JIT Compiler になりました**。V8 チームはこれに興奮して [Launching Ignition and TurboFan](https://v8.dev/blog/launching-ignition-and-turbofan) という記事を公開しました。インタプリタ実行も、ついに V8 Engine が JS コードを実行するデフォルトの方法になりました。

![](https://s2.loli.net/2025/03/11/CX81DoyTBaeV46n.png)

> その後、コンパイルパイプラインにはほとんど変化がなく、開発者たちは何も言わず、ただこの 2 つの大きな山の手直しを黙々と続けています......