# Chromium

## 概要

[Chromium](https://www.chromium.org/Home/) は [The Chromium Projects](https://www.chromium.org/chromium-projects/) 配下のオープンソースのブラウザプロジェクトです。BSD 3-clause を含む複数のライセンスを使用しており、主な記述言語は C++ で、ソースコードは [https://chromium.googlesource.com/chromium/src/+/HEAD/docs/get_the_code.md](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/get_the_code.md) から入手できます。

[Google Chrome](https://www.google.com/chrome/) は、Google が Chromium をもとに開発したブラウザです。Google の開発者は、Google 独自のコード(Google アカウント、タブの同期、メディアデコーダなどの機能)を追加し、Google の独自プロジェクトにしています。

現在、世界で活発に使われているブラウザのほとんどは Chromium をもとに開発されており(chromium をエンジンとして使用)、独自のブラウザエンジンを手放した [Microsoft Edge](https://www.microsoft.com/en-us/edge/) もその 1 つです。他のエンジンを使い続けているのは [Firefox](https://www.mozilla.org/en-US/firefox/new/) と [Safari](https://www.apple.com/safari/) だけです。

![](https://s2.loli.net/2025/03/08/3u7rOs6j4gQJzRa.png)

――しかし実際には、ブラウザはこのように一言二言でまとめられるものではありません。Chromium 自体は完全なブラウザプロジェクトで、そのレンダリングエンジンは [Blink](https://www.chromium.org/blink/) です。これは Microsoft が主に Chromium に頼っている部分でもあります(IE 時代の Trident エンジンから派生した独自の EdgeHTML エンジンは、正直いまひとつだったためです)。対応して、Safari のレンダリングエンジンは[オープンソースの WebKit](https://webkit.org/)、Firefox のレンダリングエンジンは[オープンソースの Gecko](https://firefox-source-docs.mozilla.org/overview/gecko.html) です。ただし、これ以外の JavaScript エンジンについては、Microsoft は Chromium の [V8](https://v8.dev/) ではなく、自社開発の[オープンソースの Chakra](https://github.com/chakra-core/ChakraCore) を使っていました( ~~うわ、二次元(オタク)的なものがこんなに多いなんて~~ )。同様に、Safari の JS エンジンは自社の [Nitro]()、Firefox の JS エンジンは自社開発の[オープンソースの SpiderMonkey](https://spidermonkey.dev/) です......

> これが、自社開発のブラウザというと通常は 4 つしかないとされる理由です。chromium をベースに外観だけ変えてブランドを付けた、いわゆる「自社開発」のブラウザは、独自の組版エンジンもなければ、独自の JS エンジンもなく、独自のネットワークスタックもありません...要するに、コアな部分はどれも自社開発ではないので、それは果たして少し

では、ブラウザはどのように動作しているのでしょうか。「HTML ファイルを取得して解析し、画面に描画するだけでしょう」と考える人もいるかもしれません。レンダリングエンジンだけに限って言えば、**確かに**そのようにまとめられそうです。レンダリングエンジンは、サーバから送られてきた HTML、CSS、JS ファイルなどを取り込み、解析したうえで GPU に渡して画面に描画させます。

![](https://s2.loli.net/2025/03/08/6ObUMxFAh5Tkvw1.png)

少し展開すると、次のようになります(HTTP Client がブラウザです)。

![](https://s2.loli.net/2025/03/08/OLtXs5rTjk2i7pG.png)

HTML を解析すると内容を表す DOM Tree が得られ、CSS を解析するとレイアウトを表す CSSOM Tree が得られます。両者を合わせると具体的な描画情報を含む Render Tree になり、さらに JS Engine が動的な内容の調整やさまざまな裏方の処理を行うことで、現代のブラウザの原型ができあがります。

![](https://s2.loli.net/2025/03/08/6agfHueKnjmJCB1.png)

ただ、コンパイラの原理を学び始めたばかりの学部生でも、再帰下降で簡易的な解析エンジンを手作りできそうに見えますが、実際には、現代の Web 標準を実装し、さらに十分高い性能を出すには、背後の作業量はほとんどの人が想像するよりはるかに多くなります。ブラウザの背後にあるネットワークプロトコルスタック、メモリ管理とマルチプロセスアーキテクチャ、レンダリングエンジンや JS エンジンの実装の詳細は、どれも一部を取り出すだけで何本もの論文が書けるほどです。理論上、すべての部分を 1 人の開発者で説明しきれる人はいないはずです。また、本稿の焦点はブラウザ全体がどう動作するかではないので、ここでは深入りしません :)

![](https://s2.loli.net/2025/03/08/AxTcI3XVnUyZ68l.png)

## Chromium Render Process

Chromium の実行アーキテクチャは、おおよそ次の図のとおりです(これらのプロセス間の通信は、通常 IPC Engine である [Mojo](https://chromium.googlesource.com/chromium/src/+/lkgr/mojo/README.md) を通じて行われます)。

![なぜこんなにアニメ調なのか。筆者がほかに適切な図を見つけられなかったためです...](https://s2.loli.net/2025/03/08/63bwqkTr1WAXm5g.png)

Browser Process は、ネットワークリクエストの処理、ストレージ管理、UI などを担当します(上図の左・中・右の 3 つのスレッド)。ネットワークリクエストの内容の受信が完了すると、ページのデータを Render Process に渡してレンダリングさせます。

![](https://s2.loli.net/2025/03/08/wj6VW8IsRpQlG4Y.png)

Render Process はまず HTML、CSS、JavaScript の内容を解析します。前に述べたように HTML の解析は最終的に DOM Tree を生成します。そして JavaScript は、このとき **HTML の解析をブロックし、優先的に解析・実行されます**。JS コードが文書の内容を変更する可能性があるためです(たとえば `document.write()` を使う場合)。

> HTML に埋め込んだ JS コードが `document.write()` を使わないのであれば、`<script>` タグに [async](https://developer.mozilla.org/docs/Web/HTML/Element/script#attr-async) または [defer](https://developer.mozilla.org/docs/Web/HTML/Element/script#attr-defer) 属性を使うことで、JS を非同期に実行して解析をブロックしないようにできます

![](https://s2.loli.net/2025/03/08/hcvo3XOuCgVNs1k.png)

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
