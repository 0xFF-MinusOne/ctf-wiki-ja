# Ignition Interpreter

[Ignition Interpreter](https://v8.dev/blog/ignition-interpreter) は V8 の JS インタプリタです。Parser フロントエンドが生成した抽象構文木をまずバイトコードに変換し、その後でバイトコードをインタプリタ実行します。処理のパイプラインは次の図のとおりです。

![](https://s2.loli.net/2025/03/09/D2ibKIsxh1zPZVF.png)

- まず、Parser が生成した抽象構文木を基本的なバイトコードに変換します。Ignition の仮想マシンは、最も一般的なレジスタマシン(register machine。バイトコードの入力と出力がレジスタオペランドとして明示的に指定される)として設計されています
- 次に、バイトコードは一連の中間最適化の段階を通ります
    - まず、バイトコードが使うレジスタの最適化です。たとえば、不要なレジスタ間のコピーを減らします
    - 次に、命令列の最適化です。命令列を、等価でより優れた命令に置き換えます。これには、無駄な操作の削除や、等価な操作の簡略化などが含まれます
    - 最後に、一般的なデッドコード除去の段階です。たとえば、実行されないコードや使われない変数を取り除きます
- 最適化が完了すると、Ignition Interpreter がバイトコードをインタプリタ実行します

>  これら一連の作業は、バックグラウンドの Script Streamer Thread で並行して実行されるため、フォアグラウンドのメインスレッドへの負荷が減ることに注意してください。

## Ignition Bytecodes

Ignition Bytecode は固定長の命令セットで、その背後にあるマシンアーキテクチャは最も一般的なレジスタマシンとして設計されています。bytecode の完全な一覧は次の図のとおりです。

![](https://s2.loli.net/2025/03/11/Nm7DB84FzYrZJL2.png)

たとえば、次は JS コードを Ignition Bytecode に変換した例です(初期状態)。

![](https://s2.loli.net/2025/03/11/gnlRaNOybFAYmVT.png)

## Why Interpret？

実は、**Ignition が登場する前は、JS は最適化されていないマシンコードに直接変換されており**、必要に応じて TurboFan などが最適化していました(Ignition を有効にしない場合、V8 は今でもこのように動作します)。Ignition Interpreter の登場は V8 の中核となる実行ロジックを変えました。**では、なぜインタプリタ実行を使うのでしょうか。**

これは主に次のような考慮によるものです。

- Ignition のバイトコードが占めるメモリ領域は、より小さい(ベースラインのマシンコードの 25～50%)
- Ignition のバイトコードへの変換は、より速い(少なくとも、マシンコードへの変換よりは速い)
- Ignition のバイトコードは複雑さがより低く、コンパイルパイプラインを簡素化できる

> 作成中です。

## Reference

https://arttnba3.cn

[What Are Rendering Engines: An In-Depth Guide](https://www.lambdatest.com/learning-hub/rendering-engines)

[RenderingNG deep-dive: BlinkNG](https://developer.chrome.com/docs/chromium/blinkng)

[How Does the Browser Render HTML?](https://component-odyssey.com/tips/02-how-does-the-browser-render-html)

[Browser's Rendering Pipeline](https://www.figma.com/community/file/1327562660128482813/browsers-rendering-pipeline)

[Inside look at modern web browser (part 1) ](https://developer.chrome.com/blog/inside-browser-part1)

[JavaScript engine fundamentals: Shapes and Inline Caches](https://mathiasbynens.be/notes/shapes-ics)

[Winty's blog - 現代ブラウザのアーキテクチャ雑談](https://github.com/LuckyWinty/blog/blob/master/markdown/Q%26A/%E7%8E%B0%E4%BB%A3%E6%B5%8F%E8%A7%88%E5%99%A8%E6%9E%B6%E6%9E%84%E6%BC%AB%E8%B0%88.md)

[Firing up the Ignition interpreter](https://v8.dev/blog/ignition-interpreter)

[Digging into the TurboFan JIT](https://v8.dev/blog/turbofan-jit)

[Ignition: Jump-starting an Interpreter for V8](https://docs.google.com/presentation/d/1HgDDXBYqCJNasBKBDf9szap1j4q4wnSHhOYpaNy5mHU/edit#slide=id.g1357e6d1a4_0_58)

[Ignition: An Interpreter for V8](https://docs.google.com/presentation/d/1OqjVqRhtwlKeKfvMdX6HaCIu9wpZsrzqpIVIwQSuiXQ/edit#slide=id.g1357e6d1a4_0_58)

[Deoptimization in V8](https://docs.google.com/presentation/d/1Z6oCocRASCfTqGq1GCo1jbULDGS-w-nzxkbVF7Up0u0/htmlpresent) 

[A New Crankshaft for V8](https://blog.chromium.org/2010/12/new-crankshaft-for-v8.html)

[TurboFan](https://v8.dev/docs/turbofan)

[Sea of Nodes](https://darksi.de/d.sea-of-nodes/)

[TurboFan: A new code generation architecture for V8](https://docs.google.com/presentation/d/1_eLlVzcj94_G4r9j9d_Lj5HRKFnq6jgpuPJtnmIBs88/edit#slide=id.g2134da681e_0_125)