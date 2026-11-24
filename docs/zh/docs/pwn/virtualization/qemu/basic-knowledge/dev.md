# QEMU デバイスエミュレーション

QEMU はユーザー空間で独立してデバイスをエミュレートし、仮想デバイスは、ほかの VM から hypervisor が提供するインターフェースを通じて呼び出されます。デバイスのエミュレーションは hypervisor から独立しているため、任意のデバイスをエミュレートでき、そのエミュレートされたデバイスはほかの hypervisor 間でも共有できます。

この章では、QEMU がどのようにデバイスエミュレーションを行うかを説明します。

## QEMU のデバイス IO 処理

VM が仮想デバイスに対応する物理メモリ/ポートにアクセスすると、制御は VM から Hypervisor に移り、このとき QEMU は VM-exit を引き起こしたイベントの種類に応じて異なる処理を行います。

> accel/kvm/kvm-all.c

```c
int kvm_cpu_exec(CPUState *cpu)
{
    //...

    do {
        //...

        run_ret = kvm_vcpu_ioctl(cpu, KVM_RUN, 0);

        // VCPU が実行を終了したので、対応するイベントを処理する

        trace_kvm_run_exit(cpu->cpu_index, run->exit_reason);
        switch (run->exit_reason) {
        case KVM_EXIT_IO:
            DPRINTF("handle_io\n");
            /* Called outside BQL */
            kvm_handle_io(run->io.port, attrs,
                          (uint8_t *)run + run->io.data_offset,
                          run->io.direction,
                          run->io.size,
                          run->io.count);
            ret = 0;
            break;
        case KVM_EXIT_MMIO:
            DPRINTF("handle_mmio\n");
            /* Called outside BQL */
            address_space_rw(&address_space_memory,
                             run->mmio.phys_addr, attrs,
                             run->mmio.data,
                             run->mmio.len,
                             run->mmio.is_write);
            ret = 0;
            break;
```

### MMIO

MMIO の場合は `address_space_rw()` 関数が呼び出されます。この関数はまずグローバルアドレス空間 `address_space_memory` を `FlatView` に展開し、その後、対応する関数を呼び出して読み書き操作を行います。

> softmmu/physmem.c

```c
MemTxResult address_space_read_full(AddressSpace *as, hwaddr addr,
                                    MemTxAttrs attrs, void *buf, hwaddr len)
{
    MemTxResult result = MEMTX_OK;
    FlatView *fv;

    if (len > 0) {
        RCU_READ_LOCK_GUARD();
        fv = address_space_to_flatview(as);
        result = flatview_read(fv, addr, attrs, buf, len);
    }

    return result;
}

MemTxResult address_space_write(AddressSpace *as, hwaddr addr,
                                MemTxAttrs attrs,
                                const void *buf, hwaddr len)
{
    MemTxResult result = MEMTX_OK;
    FlatView *fv;

    if (len > 0) {
        RCU_READ_LOCK_GUARD();
        fv = address_space_to_flatview(as);
        result = flatview_write(fv, addr, attrs, buf, len);
    }

    return result;
}

MemTxResult address_space_rw(AddressSpace *as, hwaddr addr, MemTxAttrs attrs,
                             void *buf, hwaddr len, bool is_write)
{
    if (is_write) {
        return address_space_write(as, addr, attrs, buf, len);
    } else {
        return address_space_read_full(as, addr, attrs, buf, len);
    }
}
```

操作関数は最終的に `FlatView` に基づいて、対象のメモリに対応する `MemoryRegion` を見つけます。関数テーブルに読み書きのポインタが定義されている MR については、最後に対応する関数ポインタを呼び出してメモリアクセスを行います。コードが多いため、ここではこれ以上展開しません。

> softmmu/physmem.c

```c
/* Called from RCU critical section.  */
static MemTxResult flatview_write(FlatView *fv, hwaddr addr, MemTxAttrs attrs,
                                  const void *buf, hwaddr len)
{
    hwaddr l;
    hwaddr addr1;
    MemoryRegion *mr;

    l = len;
    mr = flatview_translate(fv, addr, &addr1, &l, true, attrs);
    if (!flatview_access_allowed(mr, attrs, addr, len)) {
        return MEMTX_ACCESS_ERROR;
    }
    return flatview_write_continue(fv, addr, attrs, buf, len,
                                   addr1, l, mr);
}

/* Called from RCU critical section.  */
static MemTxResult flatview_read(FlatView *fv, hwaddr addr,
                                 MemTxAttrs attrs, void *buf, hwaddr len)
{
    hwaddr l;
    hwaddr addr1;
    MemoryRegion *mr;

    l = len;
    mr = flatview_translate(fv, addr, &addr1, &l, false, attrs);
    if (!flatview_access_allowed(mr, attrs, addr, len)) {
        return MEMTX_ACCESS_ERROR;
    }
    return flatview_read_continue(fv, addr, attrs, buf, len,
                                  addr1, l, mr);
}
```

### PMIO

`PMIO` の場合は `kvm_handle_io()` 関数が呼び出されます。この関数も実際には `address_space_rw()` のラッパーですが、使うのは**ポートアドレス空間** `address_space_io` で、最終的には対応する `MemoryRegion` の関数テーブルにある読み書き関数が呼び出されます。

```c
static void kvm_handle_io(uint16_t port, MemTxAttrs attrs, void *data, int direction,
                          int size, uint32_t count)
{
    int i;
    uint8_t *ptr = data;

    for (i = 0; i < count; i++) {
        address_space_rw(&address_space_io, port, attrs,
                         ptr, size,
                         direction == KVM_EXIT_IO_OUT);
        ptr += size;
    }
}
```

## QEMU PCI デバイス

> 執筆中。

## REFERENCE

『QEMU/KVM ソースコード解析と応用』——李強 著

[【HARDWARE.0x00】PCI 设备简易食用手册](https://arttnba3.cn/2022/08/30/HARDWARE-0X00-PCI_DEVICE/)

[【VIRT.0x02】系统虚拟化导论](https://arttnba3.cn/2022/08/29/VURTUALIZATION-0X02-BASIC_KNOWLEDGE)
