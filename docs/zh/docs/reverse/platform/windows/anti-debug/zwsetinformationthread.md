# ZwSetInformationThread

## ZwSetInformationThread について

ZwSetInformationThread は NtSetInformationThread と同等で、スレッドに ThreadHideFromDebugger を設定することで、そのスレッドがデバッグイベントを生成するのを禁止できます。コードは次のとおりです。  
```c
#include <Windows.h>
#include <stdio.h>

typedef DWORD(WINAPI* ZW_SET_INFORMATION_THREAD) (HANDLE, DWORD, PVOID, ULONG);
#define ThreadHideFromDebugger 0x11
VOID DisableDebugEvent(VOID)
{
    HINSTANCE hModule;
    ZW_SET_INFORMATION_THREAD ZwSetInformationThread;
    hModule = GetModuleHandleA("Ntdll");
    ZwSetInformationThread = (ZW_SET_INFORMATION_THREAD)GetProcAddress(hModule, "ZwSetInformationThread");
    ZwSetInformationThread(GetCurrentThread(), ThreadHideFromDebugger, 0, 0);
}

int main()
{
    printf("Begin\n");
    DisableDebugEvent();
    printf("End\n");
    return 0;
}
```

重要なコードは `ZwSetInformationThread(GetCurrentThread(), ThreadHideFromDebugger, 0, 0);` です。デバッグ状態にある場合、この行を実行し終えると、プログラムは終了します。  

## 回避の方法

ここでの ZwSetInformationThread 関数の第 2 引数は ThreadHideFromDebugger で、その値は 0x11 であることに注意します。デバッグしながらこの関数まで実行したとき、第 2 引数の値が 0x11 であるのを見つけたら、その呼び出しをスキップするか、0x11 を別の値に書き換えればよいのです。  