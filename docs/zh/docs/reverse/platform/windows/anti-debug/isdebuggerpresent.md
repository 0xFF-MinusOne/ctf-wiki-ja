# IsDebuggerPresent

## IsDebuggerPresent について

デバッガが存在するとき、`kernel32` の `IsDebuggerPresent()` 関数は `0 以外の値` を返します。

``` c++
BOOL WINAPI IsDebuggerPresent(void);
```

## 検出コード

検出方法は非常に簡単で、たとえば次のコード(32ビットでも64ビットでも同じコードです)で32ビット・64ビット環境の検出ができます。

``` asm
call IsDebuggerPresent
test al, al
jne being_debugged
```

実際には、この関数は `BeingDebugged` フラグの値をそのまま返しているだけです。`BeingDebugged` フラグを調べる方法は、32ビット環境なら次の32ビットコードでも実現できます。

``` asm
mov eax, fs:[30h] ;Process Environment Block
cmp b [eax+2], 0 ;check BeingDebugged
jne being_debugged
```

64ビット環境なら、次の64ビットコードを使います。

``` asm
push 60h
pop rsi
gs:lodsq ;Process Environment Block
cmp b [rax+2], 0 ;check BeingDebugged
jne being_debugged
```

64ビット環境を32ビットコードで検出する場合は、次のようにします。

``` asm
mov eax, fs:[30h] ;Process Environment Block
;64-bit Process Environment Block
;follows 32-bit Process Environment Block
cmp b [eax+1002h], 0 ;check BeingDebugged
jne being_debugged
```

## 回避の方法

これらの検出を回避するには、`BeingDebugged` フラグを `0` に設定するだけです(または戻り値を変更します)。