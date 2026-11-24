# Detecting Breakpoints

gdb は、対象アドレスのバイトを `0xcc` に置き換えることでブレークポイントを実現しています。ここでは、`int 3` ブレークポイントを検出する簡単な例を示します。

``` c
void foo() {
    printf("Hello\n");
}
int main() {
    if ((*(volatile unsigned *)((unsigned)foo) & 0xff) == 0xcc) {
        printf("BREAKPOINT\n");
        exit(1);
    }
    foo();
}
```

通常どおり実行すると Hello と出力されます。しかし、事前に `foo` 関数に `cc` ブレークポイントを設定して実行すると、gdb は停止できず、`BREAKPOINT` と出力されます。

```
# gdb ./x
gdb> bp foo
Breakpoint 1 at 0x804838c
gdb> run
BREAKPOINT
Program exited with code 01.
```

これを回避するのも簡単で、アセンブリコードを読み、`foo` 関数の入口にブレークポイントを設定しないようにするだけです。実際には、ブレークポイントの検出がどこで行われているかによります。

このようなブレークポイント監視型のアンチデバッグ技術では、回避の方法よりも、それをどう見つけるかが重要です。この例では簡単に気付けますし、プログラムも対応するメッセージを出力します。実際には、プログラムは何も出力せず、ブレークポイントでも簡単には停止できません。`perl` スクリプトで、逆アセンブルしたコードから `0xcc` に関係する部分を抽出して調べることができます。

perl スクリプトで、逆アセンブルしたコードから 0xcc に関係する部分を抽出して調べることができます。


``` perl
#!/usr/bin/perl
while(<>)
{
    if($_ =~ m/([0-9a-f][4]:\s*[0-9a-f \t]*.*0xcc)/ ){ print; }
}
```

実行結果

```
# objdump -M intel -d xxx | ./antibp.pl
      80483be: 3d cc 00 00 00 cmp eax,0xcc
```

検出できたら、0xcc を 0x00 や 0x90 に書き換えることも、好きな操作を行うこともできます。

0xcc を書き換えることにも問題が生じる場合があります。前の記事で紹介したように、プログラムがファイルの検証を行っていれば、書き換えは検出されます。場合によっては、プログラムは関数の入口だけでなく、ループで関数全体を検査していることもあります。

そこで、16進エディタで、停止させたい位置に(`int 3` ではなく)`ICEBP(0xF1)` のバイトを手動で置くこともできます。`ICEBP` でも gdb を停止させられるためです。



> Reference: [Beginners Guide to Basic Linux Anti Anti Debugging Techniques](http://www.stonedcoder.org/~kd/lib/14-61-1-PB.pdf)