# NtQueryInformationProcess


``` c++
NTSTATUS WINAPI NtQueryInformationProcess(
  _In_      HANDLE           ProcessHandle,
  _In_      PROCESSINFOCLASS ProcessInformationClass,
  _Out_     PVOID            ProcessInformation,
  _In_      ULONG            ProcessInformationLength,
  _Out_opt_ PULONG           ReturnLength
);
```

## ProcessDebugPort

`ntdll` の未公開の `NtQueryInformationProcess()` 関数は、問い合わせのために情報クラスの引数を受け取ります。`ProcessDebugPort(7)` はその情報クラスの1つです。`kernel32` の `CheckRemoteDebuggerPresent()` 関数は、内部で `NtQueryInformationProcess()` を呼び出してデバッグを検出しており、`NtQueryInformationProcess` は内部で `EPROCESS` 構造体の `DebugPort` フィールドを調べます。プロセスがデバッグされているとき、戻り値は `0xffffffff` になります。

32ビット環境では、次の32ビットコードで検出できます。

``` asm
push eax
mov eax, esp
push 0
push 4 ;ProcessInformationLength
push eax
push 7 ;ProcessDebugPort
push -1 ;GetCurrentProcess()
call NtQueryInformationProcess
pop eax
inc eax
je being_debugged
```

64ビット環境では、次の64ビットコードで検出します。

``` asm
xor ebp, ebp
enter 20h, 0
push 8 ;ProcessInformationLength
pop r9
push rbp
pop r8
push 7 ;ProcessDebugPort
pop rdx
or rcx, -1 ;GetCurrentProcess()
call NtQueryInformationProcess
leave
test ebp, ebp
jne being_debugged
```

情報はカーネルから渡されるため、ユーザーモードのコードには、この関数によるデバッガの検出を簡単に防ぐ方法がありません。

## ProcessDebugObjectHandle

Windows XP では `デバッグオブジェクト` が導入され、デバッグセッションが開始されると、`debug` オブジェクトとそれに関連付けられたハンドルが同時に作成されます。`ProcessDebugObjectHandle (0x1e)` クラスを使って、このハンドルの値を問い合わせられます。

32ビット環境では、次の32ビットコードで検出できます。

``` asm
push 0
mov eax, esp
push 0
push 4 ;ProcessInformationLength
push eax
push 1eh ;ProcessDebugObjectHandle
push -1 ;GetCurrentProcess()
call NtQueryInformationProcess
pop eax
test eax, eax
jne being_debugged
```

64ビット環境では、次の64ビットコードで検出します。

``` asm
xor ebp, ebp
enter 20h, 0
push 8 ;ProcessInformationLength
pop r9
push rbp
pop r8
push 1eh ;ProcessDebugObjectHandle
pop rdx
or rcx, -1 ;GetCurrentProcess()
call NtQueryInformationProcess
leave
test ebp, ebp
jne being_debugged
```

## ProcessDebugFlags

`ProcessDebugFlags (0x1f)` クラスは、`EPROCESS` 構造体の `NoDebugInherit` の反転した値を返します。つまり、デバッガが存在するときの戻り値は `0`、存在しないときは `1` です。

32ビット環境では、次の32ビットコードで検出できます。

``` asm
push eax
mov eax, esp
push 0
push 4 ;ProcessInformationLength
push eax
push 1fh ;ProcessDebugFlags
push -1 ;GetCurrentProcess()
call NtQueryInformationProcess
pop eax
test eax, eax
je being_debugged
```

64ビット環境では、次の64ビットコードで検出します。

``` asm
xor ebp, ebp
enter 20h, 0
push 4 ;ProcessInformationLength
pop r9
push rbp
pop r8
push 1fh ;ProcessDebugFlags
pop rdx
or rcx, -1 ;GetCurrentProcess()
call NtQueryInformationProcess
leave
test ebp, ebp
je being_debugged
```