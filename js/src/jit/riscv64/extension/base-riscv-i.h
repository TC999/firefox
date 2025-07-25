// Copyright 2022 the V8 project authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
#ifndef jit_riscv64_extension_Base_riscv_i_h_
#define jit_riscv64_extension_Base_riscv_i_h_
#include "mozilla/Assertions.h"

#include <stdint.h>

#include "jit/riscv64/constant/Constant-riscv64.h"
#include "jit/riscv64/extension/base-assembler-riscv.h"
namespace js {
namespace jit {

class AssemblerRISCVI : public AssemblerRiscvBase {
 public:
  void lui(Register rd, int32_t imm20);
  void auipc(Register rd, int32_t imm20);

  // Jumps
  void jal(Register rd, int32_t imm20);
  BufferOffset jalr(Register rd, Register rs1, int16_t imm12);

  // Branches
  void beq(Register rs1, Register rs2, int16_t imm12);
  void bne(Register rs1, Register rs2, int16_t imm12);
  void blt(Register rs1, Register rs2, int16_t imm12);
  void bge(Register rs1, Register rs2, int16_t imm12);
  void bltu(Register rs1, Register rs2, int16_t imm12);
  void bgeu(Register rs1, Register rs2, int16_t imm12);
  // Loads
  void lb(Register rd, Register rs1, int16_t imm12);
  void lh(Register rd, Register rs1, int16_t imm12);
  void lw(Register rd, Register rs1, int16_t imm12);
  void lbu(Register rd, Register rs1, int16_t imm12);
  void lhu(Register rd, Register rs1, int16_t imm12);

  // Stores
  void sb(Register source, Register base, int16_t imm12);
  void sh(Register source, Register base, int16_t imm12);
  void sw(Register source, Register base, int16_t imm12);

  // Arithmetic with immediate
  void addi(Register rd, Register rs1, int16_t imm12);
  void slti(Register rd, Register rs1, int16_t imm12);
  void sltiu(Register rd, Register rs1, int16_t imm12);
  void xori(Register rd, Register rs1, int16_t imm12);
  void ori(Register rd, Register rs1, int16_t imm12);
  void andi(Register rd, Register rs1, int16_t imm12);
  void slli(Register rd, Register rs1, uint8_t shamt);
  void srli(Register rd, Register rs1, uint8_t shamt);
  void srai(Register rd, Register rs1, uint8_t shamt);

  // Arithmetic
  void add(Register rd, Register rs1, Register rs2);
  void sub(Register rd, Register rs1, Register rs2);
  void sll(Register rd, Register rs1, Register rs2);
  void slt(Register rd, Register rs1, Register rs2);
  void sltu(Register rd, Register rs1, Register rs2);
  void xor_(Register rd, Register rs1, Register rs2);
  void srl(Register rd, Register rs1, Register rs2);
  void sra(Register rd, Register rs1, Register rs2);
  void or_(Register rd, Register rs1, Register rs2);
  void and_(Register rd, Register rs1, Register rs2);

  // Other pseudo instructions that are not part of RISCV pseudo assemly
  void nor(Register rd, Register rs, Register rt) {
    or_(rd, rs, rt);
    not_(rd, rd);
  }

  // Memory fences
  void fence(uint8_t pred, uint8_t succ);
  void fence_tso();

  // Environment call / break
  void ecall();
  void ebreak();

  void sync() { fence(0b1111, 0b1111); }

  // This is a de facto standard (as set by GNU binutils) 32-bit unimplemented
  // instruction (i.e., it should always trap, if your implementation has
  // invalid instruction traps).
  void unimp();

  static int JumpOffset(Instr instr);
  static int AuipcOffset(Instr instr);
  static int JalrOffset(Instr instr);
  static int LoadOffset(Instr instr);
  static int BranchOffset(Instr instr);
  static int BrachlongOffset(Instr auipc, Instr instr_I);
  static inline Instr SetBranchOffset(int32_t pos, int32_t target_pos,
                                      Instr instr) {
    int32_t imm = target_pos - pos;
    MOZ_ASSERT((imm & 1) == 0);
    MOZ_ASSERT(is_intn(imm, kBranchOffsetBits));

    instr &= ~kBImm12Mask;
    int32_t imm12 = ((imm & 0x800) >> 4) |   // bit  11
                    ((imm & 0x1e) << 7) |    // bits 4-1
                    ((imm & 0x7e0) << 20) |  // bits 10-5
                    ((imm & 0x1000) << 19);  // bit 12

    return instr | (imm12 & kBImm12Mask);
  }

  static inline Instr SetJalOffset(int32_t pos, int32_t target_pos,
                                   Instr instr) {
    MOZ_ASSERT(IsJal(instr));
    int32_t imm = target_pos - pos;
    MOZ_ASSERT((imm & 1) == 0);
    MOZ_ASSERT(is_intn(imm, kJumpOffsetBits));

    instr &= ~kImm20Mask;
    int32_t imm20 = (imm & 0xff000) |          // bits 19-12
                    ((imm & 0x800) << 9) |     // bit  11
                    ((imm & 0x7fe) << 20) |    // bits 10-1
                    ((imm & 0x100000) << 11);  // bit  20

    return instr | (imm20 & kImm20Mask);
  }

  static inline Instr SetJalrOffset(int32_t offset, Instr instr) {
    MOZ_ASSERT(IsJalr(instr));
    MOZ_ASSERT(is_int12(offset));
    instr &= ~kImm12Mask;
    int32_t imm12 = offset << kImm12Shift;
    MOZ_ASSERT(IsJalr(instr | (imm12 & kImm12Mask)));
    MOZ_ASSERT(JalrOffset(instr | (imm12 & kImm12Mask)) == offset);
    return instr | (imm12 & kImm12Mask);
  }

  static inline Instr SetLoadOffset(int32_t offset, Instr instr) {
#if JS_CODEGEN_RISCV64
    MOZ_ASSERT(IsLd(instr));
#elif JS_CODEGEN_RISCV32
    MOZ_ASSERT(IsLw(instr));
#endif
    MOZ_ASSERT(is_int12(offset));
    instr &= ~kImm12Mask;
    int32_t imm12 = offset << kImm12Shift;
    return instr | (imm12 & kImm12Mask);
  }

  static inline Instr SetAuipcOffset(int32_t offset, Instr instr) {
    MOZ_ASSERT(IsAuipc(instr));
    MOZ_ASSERT(is_int20(offset));
    instr = (instr & ~kImm31_12Mask) | ((offset & kImm19_0Mask) << 12);
    return instr;
  }

  // Check if an instruction is a branch of some kind.
  static bool IsBranch(Instr instr);
  static bool IsNop(Instr instr);
  static bool IsJump(Instr instr);
  static bool IsJal(Instr instr);
  static bool IsJalr(Instr instr);
  static bool IsLui(Instr instr);
  static bool IsAuipc(Instr instr);
  static bool IsAddi(Instr instr);
  static bool IsOri(Instr instr);
  static bool IsSlli(Instr instr);
  static bool IsLw(Instr instr);

  inline int32_t branch_offset(Label* L) {
    return branch_offset_helper(L, OffsetSize::kOffset13);
  }
  inline int32_t jump_offset(Label* L) {
    return branch_offset_helper(L, OffsetSize::kOffset21);
  }

  // Branches
  void beq(Register rs1, Register rs2, Label* L) {
    beq(rs1, rs2, branch_offset(L));
  }
  void bne(Register rs1, Register rs2, Label* L) {
    bne(rs1, rs2, branch_offset(L));
  }
  void blt(Register rs1, Register rs2, Label* L) {
    blt(rs1, rs2, branch_offset(L));
  }
  void bge(Register rs1, Register rs2, Label* L) {
    bge(rs1, rs2, branch_offset(L));
  }
  void bltu(Register rs1, Register rs2, Label* L) {
    bltu(rs1, rs2, branch_offset(L));
  }
  void bgeu(Register rs1, Register rs2, Label* L) {
    bgeu(rs1, rs2, branch_offset(L));
  }

  void beqz(Register rs, int16_t imm13) { beq(rs, zero_reg, imm13); }
  void beqz(Register rs1, Label* L) { beqz(rs1, branch_offset(L)); }
  void bnez(Register rs, int16_t imm13) { bne(rs, zero_reg, imm13); }
  void bnez(Register rs1, Label* L) { bnez(rs1, branch_offset(L)); }
  void blez(Register rs, int16_t imm13) { bge(zero_reg, rs, imm13); }
  void blez(Register rs1, Label* L) { blez(rs1, branch_offset(L)); }
  void bgez(Register rs, int16_t imm13) { bge(rs, zero_reg, imm13); }
  void bgez(Register rs1, Label* L) { bgez(rs1, branch_offset(L)); }
  void bltz(Register rs, int16_t imm13) { blt(rs, zero_reg, imm13); }
  void bltz(Register rs1, Label* L) { bltz(rs1, branch_offset(L)); }
  void bgtz(Register rs, int16_t imm13) { blt(zero_reg, rs, imm13); }

  void bgtz(Register rs1, Label* L) { bgtz(rs1, branch_offset(L)); }
  void bgt(Register rs1, Register rs2, int16_t imm13) { blt(rs2, rs1, imm13); }
  void bgt(Register rs1, Register rs2, Label* L) {
    bgt(rs1, rs2, branch_offset(L));
  }
  void ble(Register rs1, Register rs2, int16_t imm13) { bge(rs2, rs1, imm13); }
  void ble(Register rs1, Register rs2, Label* L) {
    ble(rs1, rs2, branch_offset(L));
  }
  void bgtu(Register rs1, Register rs2, int16_t imm13) {
    bltu(rs2, rs1, imm13);
  }
  void bgtu(Register rs1, Register rs2, Label* L) {
    bgtu(rs1, rs2, branch_offset(L));
  }
  void bleu(Register rs1, Register rs2, int16_t imm13) {
    bgeu(rs2, rs1, imm13);
  }
  void bleu(Register rs1, Register rs2, Label* L) {
    bleu(rs1, rs2, branch_offset(L));
  }

  void j(int32_t imm21) { jal(zero_reg, imm21); }
  void j(Label* L) { j(jump_offset(L)); }
  void b(Label* L) { j(L); }
  void jal(int32_t imm21) { jal(ra, imm21); }
  void jal(Label* L) { jal(jump_offset(L)); }
  void jr(Register rs) { jalr(zero_reg, rs, 0); }
  void jr(Register rs, int32_t imm12) { jalr(zero_reg, rs, imm12); }
  void jalr(Register rs, int32_t imm12) { jalr(ra, rs, imm12); }
  void jalr(Register rs) { jalr(ra, rs, 0); }
  void call(int32_t offset) {
    auipc(ra, (offset >> 12) + ((offset & 0x800) >> 11));
    jalr(ra, ra, offset << 20 >> 20);
  }

  void mv(Register rd, Register rs) { addi(rd, rs, 0); }
  void not_(Register rd, Register rs) { xori(rd, rs, -1); }
  void neg(Register rd, Register rs) { sub(rd, zero_reg, rs); }
  void seqz(Register rd, Register rs) { sltiu(rd, rs, 1); }
  void snez(Register rd, Register rs) { sltu(rd, zero_reg, rs); }
  void sltz(Register rd, Register rs) { slt(rd, rs, zero_reg); }
  void sgtz(Register rd, Register rs) { slt(rd, zero_reg, rs); }

#if JS_CODEGEN_RISCV64
  void lwu(Register rd, Register rs1, int16_t imm12);
  void ld(Register rd, Register rs1, int16_t imm12);
  void sd(Register source, Register base, int16_t imm12);
  void addiw(Register rd, Register rs1, int16_t imm12);
  void slliw(Register rd, Register rs1, uint8_t shamt);
  void srliw(Register rd, Register rs1, uint8_t shamt);
  void sraiw(Register rd, Register rs1, uint8_t shamt);
  void addw(Register rd, Register rs1, Register rs2);
  void subw(Register rd, Register rs1, Register rs2);
  void sllw(Register rd, Register rs1, Register rs2);
  void srlw(Register rd, Register rs1, Register rs2);
  void sraw(Register rd, Register rs1, Register rs2);
  void negw(Register rd, Register rs) { subw(rd, zero_reg, rs); }
  void sext_w(Register rd, Register rs) { addiw(rd, rs, 0); }

  static bool IsAddiw(Instr instr);
  static bool IsLd(Instr instr);
#endif
};

}  // namespace jit
}  // namespace js

#endif  // jit_riscv64_extension_Base_riscv_I_h_
