# Detecting debugging

デバッガを検出する方法はたくさんあり、たとえばプロセス名の検査などがあります。ここでは、いくつかの関数の呼び出し状況を検査して、プログラムが現在デバッグされている状態かどうかを調べる方法を紹介します。

```c 
int main()
{
	if (ptrace(PTRACE_TRACEME, 0, 1, 0) < 0) {
		printf("DEBUGGING... Bye\n");
		return 1;
	}
	printf("Hello\n");
	return 0;
}
```

1つのプロセスは1つのプロセスからしか ptrace できません。自分で ptrace を呼び出しておけば、ほかのプログラムは ptrace でデバッグしたり、プログラムにコードを注入したりできなくなります。

プログラムが現在 gdb でデバッグされていると、ptrace 関数はエラーを返します。これは間接的に、デバッガの存在を検出したことを示します。

## 回避方法1

ptrace が作用するのは、ptrace を使うデバッガに対してだけなので、ptrace を使わないデバッガを使えばよいわけです。

パッチを当てて ptrace 関数を消すこともできます。もっと簡単なのは、ptrace の呼び出しコードか、その後の検証を消してしまうことです。

実行ファイルが(実際にはあまりないことですが)コンパイル時に -s オプション(-s オプションはシンボルテーブル情報と再配置情報をすべて取り除きます)を有効にしていなければ、状況はずっと簡単になります。この簡単な場合から解析します。

```
# objdump -t test_debug | grep ptrace
080482c0 	F *UND* 	00000075 	ptrace@@GLIBC_2.0
```

ptrace は `0x080482c0` の位置で呼び出されています。

```
# objdump -d -M intel test_debug |grep 80482c0
80482c0: 	ff 25 04 96 04 08 	jmp ds:0x8049604
80483d4: 	e8 e7 fe ff ff 	call 80482c0 <_init+0x28>
```

では、-s オプションが有効だった場合はどう処理すればよいでしょうか。このときは gdb を使う必要があります。

```
# gdb test_debug
gdb> bp ptrace
Breakpoint 1 at 0x80482c0
gdb> run
Breakpoint 1 at 0x400e02f0
......
0x400e02f0 <ptrace>: push %ebp
0x400e02f1 <ptrace+1>: mov %esp,%ebp
0x400e02f3 <ptrace+3>: sub $0x10,%esp
0x400e02f6 <ptrace+6>: mov %edi,0xfffffffc(%ebp)
0x400e02f9 <ptrace+9>: mov 0x8(%ebp),%edi
0x400e02fc <ptrace+12>: mov 0xc(%ebp),%ecx
------------------------------------------------------------------------------
Breakpoint 1, 0x400e02f0 in ptrace () from /lib/tls/libc.so.6
```

ptrace で簡単に停止できました。ここで finish と入力すると、現在の関数が戻るまで実行され、main 関数に戻ります。

```
# gdb test_debug
gdb> finish
00x80483d9 <main+29>: 	add $0x10,%esp
0x80483dc   <main+32>: 	test %eax,%eax
0x80483de   <main+34>: 	jns 0x80483fa <main+62>
0x80483e0   <main+36>: 	sub $0xc,%esp
0x80483e3   <main+39>: 	push $0x80484e8
0x80483e8   <main+44>: 	call 0x80482e0
------------------------------------------------------------------------------
0x080483d9 in main ()
```

関数の戻り値 eax を正しい戻り値に書き換えればよいのです。

```
gdb> set $eax=0
gdb> c
everything ok
Program exited with code 016.
_______________________________________________________________________________
No registers.
gdb>
```

## 回避方法2

方法2は、自分で ptrace 関数を書くことです。

前の数回の記事で述べたように、`LD_PRELOAD` 環境変数を使えば、実行ファイルが自分で用意した ptrace 関数を指すようにできます。

ptrace 関数を書いてオブジェクトファイルを生成します。

``` c
// -- ptrace.c --
// gcc -shared ptrace.c -o ptrace.so
int ptrace(int i, int j, int k, int l)
{
	printf(" PTRACE CALLED!\n");
}
```

次に、環境変数 LD_PRELOAD を設定して、自分で用意した ptrace 関数を使います。もちろん、これは gdb の中で設定できます。

```
gdb> set environment LD_PRELOAD ./ptrace.so
gdb> run
PTRACE CALLED!
Hello World!
Program exited with code 015.
gdb>
```

プログラムがデバッガを検出できなくなったことがわかります。



> Reference: [Beginners Guide to Basic Linux Anti Anti Debugging Techniques](http://www.stonedcoder.org/~kd/lib/14-61-1-PB.pdf)



