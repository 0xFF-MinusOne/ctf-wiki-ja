# Mutable Heap Numbers

**ヒープ数量不変**の仕組みは、2025 年に V8 チームが公開した最適化の仕組みです。発想は、JS のファイルシステム実装 `async-fs` が `Math.random` で遭遇した実行時のボトルネックに由来します。たとえば次のようなコードがあります。

```javascript
let seed;
Math.random = (function() {
  return function () {
    seed = ((seed + 0x7ed55d16) + (seed << 12))  & 0xffffffff;
    seed = ((seed ^ 0xc761c23c) ^ (seed >>> 19)) & 0xffffffff;
    seed = ((seed + 0x165667b1) + (seed << 5))   & 0xffffffff;
    seed = ((seed + 0xd3a2646c) ^ (seed << 9))   & 0xffffffff;
    seed = ((seed + 0xfd7046c5) + (seed << 3))   & 0xffffffff;
    seed = ((seed ^ 0xb55a4f09) ^ (seed >>> 16)) & 0xffffffff;
    return (seed & 0xfffffff) / 0x10000000;
  };
})();
```

変数 `seed` は `Math.random` を呼び出すたびに変化し、擬似乱数列を生成します。重要な点は、`seed` が `ScriptContext` の中に格納されていることです。この構造体は、特定のスクリプト内でアクセス可能な値の格納場所を表すもので(平たく言うと**JS スクリプトのコンテキスト**です)、内部は V8 のタグ付き値の配列になっています。

- ScopeInfo:コンテキストのメタデータ。
- NativeContext:グローバルオブジェクト。
- Slot 0 ～ Slot n:その他のさまざまな値。

これらの Slot の値は通常 32 ビットで、各値の最下位ビットがタグとして使われるため、使用時には値を 1 ビット右シフトします。

- 0:31 ビットの小さな整数(small interger、SMI)。
- 1:31 ビットのポインタ。

これに応じて、31 ビットを超えるデータはヒープ上に置かれ、ScriptContext の Slot にはそれらのオブジェクトへのポインタが格納されます。たとえば、単純な数値型のデータには `HeapNumber` オブジェクトが使われ、複雑なオブジェクトには `JSObject` 構造体のようなものが使われます。

![](https://s2.loli.net/2025/03/11/BEhSayrC24XJ6Tq.png)

するとボトルネックが生じます。

- **HeapNumber allocation**: 上の JS コードでは `seed` 変数が `HeapNumber` オブジェクトに格納されているため、`Math.random` 関数を呼び出すたびにメモリの確保と解放が行われます。
- **Floating-point arthmetic**: `Math.random` では終始整数演算が使われているものの、`seed` は汎用の `HeapNumber` に格納されているため、コンパイラは遅い浮動小数点演算の命令を生成します。また、コンパイラがこれは 32 ビット整数かもしれないと分かっている場合でも、64 ビット浮動小数点から 32 ビット整数への変換や、精度損失のチェックが潜在的に必要になります。

どう打開するのでしょうか。V8 チームは 2 つの最適化を採用しました。

- **Slot type tracking / mutable heap number slots**: V8 チームは [script context const value tracking](https://issues.chromium.org/u/2/issues/42203515) を拡張して型情報を含めました。これにより、slot value が定数か、`SMI` か、`HeapNumber` か、汎用のタグ付き値かを追跡します。また、スクリプトコンテキストに、`JSObjects` の [mutable heap number fields](https://v8.dev/blog/react-cliff#smi-heapnumber-mutableheapnumber) という概念の**不変ヒープ数量**という概念を導入しました。slot value は、変化する `HeapNumber` を指す状態から、**HeapNumber を保持する**状態になり、コードの最適化による更新時のヒープの再確保がなくなりました。
- **Mutable heap Int32**: V8 チームは script context slot の型を拡張して、数値が Int32 の範囲内かどうかを追跡するようにしました。範囲内であれば `HeapNumber` はそれを純粋な `Int32` として格納し、`double` への拡張が必要になった場合でも `HeapNumber` の領域を再確保する必要がありません。この場合、上の例の `Math.random` は、コンパイラの観察により、継続的に更新される整数値であることが分かるため、対応する slot を mutable `Int32` としてマークします。

注意すべきは、この最適化が context slot の値に対するコード依存を生む点です。slot の型が変わった場合(文字列になるなど)、この最適化は取り消されます。そのため、slot の型の安定性を保つことが非常に重要です( ~~要するに、JS の変数の型をしょっちゅう変えるなということです~~ )。

最終的に、`Math.random` の最適化結果は次のとおりです。

- **No allocation / fast in-place updates**: `seed` の更新で、新しいヒープオブジェクトを繰り返し確保する必要がなくなりました。
- **Integer operations**: コンパイラが型を `Int32` と把握しているため、非効率な浮動小数点演算の生成を避けられます。

最終的に、`async-fs` のベンチマークの速度は 2.5 倍になり、[JetStream2](https://browserbench.org/JetStream2.1/) というベンチマークでも全体のスコアが約 `1.6%` 向上しました。なかなか効果があります。