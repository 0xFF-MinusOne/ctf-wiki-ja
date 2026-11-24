# movofuscator

## はじめに

[movfuscator](https://github.com/xoreaxeaxeax/movfuscator) は、**通常の x86 命令を等価な mov 命令に置き換える**ことでコードを難読化するオブファスケータです。`mov` 命令はチューリング完全であるため、すべての命令を `mov` 命令からなるコード片で等価に置き換えることができ、プログラムのロジックは変わりません。

mov 難読化は特殊であるため、現時点では効率的な難読化解除の手段はまだありません。現段階では [demovfuscator](https://github.com/leetonidas/demovfuscator) などの難読化解除ツールで、初歩的な解除作業を行える程度です。

## 例題: 強網擬態 2023 決勝 - movemove

> 作成中。