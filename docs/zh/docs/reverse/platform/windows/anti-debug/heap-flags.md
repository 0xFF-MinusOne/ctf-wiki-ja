# Heap Flags

## Heap flags について

`Heap flags` には、`NtGlobalFlag` と一緒に初期化される2つのフラグ `Flags` と `ForceFlags` があります。この2つのフィールドの値は、デバッガの影響を受けるだけでなく、Windows のバージョンによっても異なり、フィールドの位置も Windows のバージョンによって決まります。

* Flags フィールド:
    * 32ビットの Windows NT、Windows 2000、Windows XP では、`Flags` はヒープのオフセット `0x0C` にあります。32ビットの Windows Vista 以降では、オフセット `0x40` にあります。
    * 64ビットの Windows XP では、`Flags` フィールドはヒープのオフセット `0x14` にあり、64ビットの Windows Vista 以降では、オフセット `0x70` にあります。
* ForceFlags フィールド:
    * 32ビットの Windows NT、Windows 2000、Windows XP では、`ForceFlags` はヒープのオフセット `0x10` にあります。32ビットの Windows Vista 以降では、オフセット `0x44` にあります。
    * 64ビットの Windows XP では、`ForceFlags` フィールドはヒープのオフセット `0x18` にあり、64ビットの Windows Vista 以降では、オフセット `0x74` にあります。

どのバージョンの Windows でも、通常、`Flags` フィールドの値は `HEAP_GROWABLE(2)` に、`ForceFlags` フィールドは `0` に設定されています。ただし32ビットのプロセスでは(64ビットのプログラムにはこの問題はありません)、この2つの既定値は、ホストプロセス(host process)の[`subsystem`](https://msdn.microsoft.com/en-us/library/ms933120.aspx)のバージョンによって決まります(ここでいうのは、たとえば Windows 10 の Linux 用サブシステムのことではありません)。`subsystem` が `3.51` 以降のバージョンの場合にだけ、フィールドの既定値は前述のとおりになります。バージョンが `3.10-3.50` の間であれば、2つのフィールドの両方に `HEAP_CREATE_ALIGN_16 (0x10000)` が設定されます。バージョンが `3.10` より低ければ、そのプログラムファイルはそもそも実行されません。

ある処理が `Flags` と `ForgeFlags` フィールドの値をそれぞれ `2` と `0` に設定しているのに、`subsystem` のバージョンを確認していなければ、その動作はデバッガを隠すために行われていると判断できます。

デバッガが存在するとき、`Windows NT`、`Windows 2000`、32ビットの `Windows XP` では、`Flags` フィールドに次のフラグが設定されます。

``` c
HEAP_GROWABLE (2)
HEAP_TAIL_CHECKING_ENABLED (0x20)
HEAP_FREE_CHECKING_ENABLED (0x40)
HEAP_SKIP_VALIDATION_CHECKS (0x10000000)
HEAP_VALIDATE_PARAMETERS_ENABLED (0x40000000)
```

64ビットの `Windows XP` と、`Windows Vista` 以降のバージョンでは、`Flags` フィールドに次のフラグが設定されます(`HEAP_SKIP_VALIDATION_CHECKS (0x10000000)` がありません)。

``` c
HEAP_GROWABLE (2)
HEAP_TAIL_CHECKING_ENABLED (0x20)
HEAP_FREE_CHECKING_ENABLED (0x40)
HEAP_VALIDATE_PARAMETERS_ENABLED (0x40000000)
```

`ForgeFlags` フィールドには、通常、次のフラグが設定されます。

``` c
HEAP_TAIL_CHECKING_ENABLED (0x20)
HEAP_FREE_CHECKING_ENABLED (0x40)
HEAP_VALIDATE_PARAMETERS_ENABLED (0x40000000)
```

`NtGlobalFlag` フラグの関係で、`heap` にもいくつかのフラグが設定されます。

* `NtGlobalFlag` フィールドに `FLG_HEAP_ENABLE_TAIL_CHECK` フラグが設定されていれば、`heap` のフィールドに `HEAP_TAIL_CHECKING_ENABLED` フラグが設定されます。
* `NtGlobalFlag` フィールドに `FLG_HEAP_ENABLE_FREE_CHECK` フラグが設定されていれば、`heap` のフィールドに `FLG_HEAP_ENABLE_FREE_CHECK` フラグが設定されます。
* `NtGlobalFlag` フィールドに `FLG_HEAP_VALIDATE_PARAMETERS` フラグが設定されていれば、`heap` のフィールドに `HEAP_VALIDATE_PARAMETERS_ENABLED` フラグが設定されます(`Windows NT` と `Windows 2000` では `HEAP_CREATE_ALIGN_16 (0x10000)` フラグも設定されます)。

`heap flags` も、前の節の `NtGlobalFlag` と同様ですが、レジストリの `HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\<filename>` にある `PageHeapFlags"` キーによって制御されます。

## heap の位置を取得する

`heap` の位置を知る方法は複数あります。その1つは `kernel32` の `GetProcessHeap()` 関数です。もちろん、32ビット環境では次の32ビットのアセンブリコードでも検出できます(実際、この API 関数を使わず、PEB を直接参照するパッカーもあります)。

``` asm
mov eax, fs:[30h] ;Process Environment Block
mov eax, [eax+18h] ;get process heap base
```

64ビット環境では、次の64ビットコードで検出できます。

``` asm
push 60h
pop rsi
gs:lodsq ;Process Environment Block
mov eax, [rax+30h] ;get process heap base
```

64ビット環境を32ビットコードで検出する場合は、次のようにします。

``` asm
mov eax, fs:[30h] ;Process Environment Block
;64-bit Process Environment Block
;follows 32-bit Process Environment Block
mov eax, [eax+1030h] ;get process heap base
```

もう1つの方法は、`kernel32` の `GetProcessHeaps()` 関数を使うことです。この関数は実際には `ntdll` の `RtlGetProcessHeaps()` 関数に処理を渡しているだけで、現在のプロセスに属するヒープの配列を返します。配列の最初のヒープは、`kernel32` の `GetProcessHeap()` 関数が返すものと同じです。



この処理は、32ビットの Windows 環境では32ビットコードで次のように実現できます。

``` asm
push 30h
pop esi
fs:lodsd ;Process Environment Block
;get process heaps list base
mov esi, [esi+eax+5ch]
lodsd
```

同様に、64ビットの Windows 環境で64ビットコードを使う場合は次のとおりです。

``` asm
push 60h
pop rsi
gs:lodsq ;Process Environment Block
;get process heaps list base
mov esi, [rsi*2+rax+20h]
lodsd
```

64ビットの Windows 環境を32ビットコードで検出する場合は次のとおりです。

``` asm
mov eax, fs:[30h] ;Process Environment Block
;64-bit Process Environment Block
;follows 32-bit Process Environment Block
mov esi, [eax+10f0h] ;get process heaps list base
lodsd
```

## Flags フィールドの検出

そうすると、デバッガの検出は、`Flags` と `ForgeFlags` のいくつかのフラグビットを調べることから始められるのは明らかです。

まず `Flags` フィールドの検出コードです。32ビットの Windows 環境を32ビットコードで検出し、`subsystem` のバージョンが `3.10-3.50` の間にある場合です。

``` asm
call GetVersion
cmp al, 6
cmc
sbb ebx, ebx
and ebx, 34h
mov eax, fs:[30h] ;Process Environment Block
mov eax, [eax+18h] ;get process heap base
mov eax, [eax+ebx+0ch] ;Flags
;neither HEAP_CREATE_ALIGN_16
;nor HEAP_SKIP_VALIDATION_CHECKS
and eax, 0effeffffh
;HEAP_GROWABLE
;+ HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp eax, 40000062h
je being_debugged
```

32ビットの Windows 環境を32ビットコードで検出し、`subsystem` が `3.51` 以降のバージョンである場合です。

``` asm
call GetVersion
cmp al, 6
cmc
sbb ebx, ebx
and ebx, 34h
mov eax, fs:[30h] ;Process Environment Block
mov eax, [eax+18h] ;get process heap base
mov eax, [eax+ebx+0ch] ;Flags
;not HEAP_SKIP_VALIDATION_CHECKS
bswap eax
and al, 0efh
;HEAP_GROWABLE
;+ HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
;reversed by bswap
cmp eax, 62000040h
je being_debugged
```

64ビットの Windows 環境を64ビットコードで検出する場合です(64ビットのプロセスは `subsystem` のバージョンに悩まされません)。

``` asm
push 60h
pop rsi
gs:lodsq ;Process Environment Block
mov ebx, [rax+30h] ;get process heap base
call GetVersion
cmp al, 6
sbb rax, rax
and al, 0a4h
;HEAP_GROWABLE
;+ HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp d [rbx+rax+70h], 40000062h ;Flags
je being_debugged
```

64ビットの Windows 環境を32ビットコードで検出する場合です。

``` asm
push 30h
pop eax
mov ebx, fs:[eax] ;Process Environment Block
;64-bit Process Environment Block
;follows 32-bit Process Environment Block
mov ah, 10h
mov ebx, [ebx+eax] ;get process heap base
call GetVersion
cmp al, 6
sbb eax, eax
and al, 0a4h
;Flags
;HEAP_GROWABLE
;+ HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp [ebx+eax+70h], 40000062h
je being_debugged
```

`KUSER_SHARED_DATA` 構造体の `NtMajorVersion` フィールド(2G のユーザー空間にあるオフセット `0x7ffe026c`)から直接この値を取得すれば(32ビット・64ビットのどのバージョンの Windows でも取得できます)、`kernel32` の `GetVersion()` 関数を呼び出す処理をさらに難読化できます。


## ForgeFlags フィールドの検出

もちろん、もう1つの方法は `ForgeFlags` フィールドを検出することです。以下は、32ビットの Windows 環境を32ビットコードで検出し、`subsystem` のバージョンが `3.10-3.50` の間にある場合です。

``` asm
call GetVersion
cmp al, 6
cmc
sbb ebx, ebx
and ebx, 34h
mov eax, fs:[30h] ;Process Environment Block
mov eax, [eax+18h] ;get process heap base
mov eax, [eax+ebx+10h] ;ForceFlags
;not HEAP_CREATE_ALIGN_16
btr eax, 10h
;HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp eax, 40000060h
je being_debugged
```

32ビットの Windows 環境を32ビットコードで検出し、`subsystem` が `3.51` 以降のバージョンである場合です。

``` asm
call GetVersion
cmp al, 6
cmc
sbb ebx, ebx
and ebx, 34h
mov eax, fs:[30h] ;Process Environment Block
mov eax, [eax+18h] ;get process heap base
;ForceFlags
;HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp [eax+ebx+10h], 40000060h
je being_debugged
```

64ビットの Windows 環境を64ビットコードで検出する場合です(64ビットのプロセスは `subsystem` のバージョンに悩まされません)。

``` asm
push 60h
pop rsi
gs:lodsq ;Process Environment Block
mov ebx, [rax+30h] ;get process heap base
call GetVersion
cmp al, 6
sbb rax, rax
and al, 0a4h
;ForceFlags
;HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp d [rbx+rax+74h], 40000060h
je being_debugged
```
64ビットの Windows 環境を32ビットコードで検出する場合です。

``` asm
call GetVersion
cmp al, 6
push 30h
pop eax
mov ebx, fs:[eax] ;Process Environment Block
;64-bit Process Environment Block
;follows 32-bit Process Environment Block
mov ah, 10h
mov ebx, [ebx+eax] ;get process heap base
sbb eax, eax
and al, 0a4h
;ForceFlags
;HEAP_TAIL_CHECKING_ENABLED
;+ HEAP_FREE_CHECKING_ENABLED
;+ HEAP_VALIDATE_PARAMETERS_ENABLED
cmp [ebx+eax+74h], 40000060h
je being_debugged
```

## 参考リンク

* [The "Ultimate" Anti-Debugging Reference](http://anti-reversing.com/Downloads/Anti-Reversing/The_Ultimate_Anti-Reversing_Reference.pdf)