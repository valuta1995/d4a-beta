from typing import Dict

from avatar2 import Target
from avatar2.plugins.cortex_m3_pretty_dump import CortexM3DumpTool


def go_go_gadget_ipython(t: Target, x: Dict[str, any] = None):
    arch = t.avatar.arch
    if x is not None:
        print(x.items())

    # noinspection PyUnresolvedReferences
    def disassemble_pretty_tool(target: Target, central_addr: int, width: int, width_after: int):
        prior_bytes = width * 2
        start_addr = central_addr - prior_bytes
        start_addr = int(start_addr / 4) * 4
        text = target.disassemble_pretty(start_addr, width + 1 + width_after)
        lines = text.split('\n')
        line: str
        for line in lines:
            is_current_line = line.startswith("0x%x" % central_addr)
            if is_current_line:
                print("")

            print(line)

            if is_current_line:
                print("")

    # noinspection PyUnresolvedReferences
    def hexon():
        """To print ints as hex, run hexon_ipython(). To revert, run hexoff_ipython()."""
        formatter = get_ipython().display_formatter.formatters['text/plain']
        formatter.for_type(int, lambda n, p, cycle: p.text("0x%08X" % n))

    # noinspection PyUnresolvedReferences
    def hexoff():
        """See documentation for hexon_ipython()."""
        formatter = get_ipython().display_formatter.formatters['text/plain']
        formatter.for_type(int, lambda n, p, cycle: p.text("%d" % n))

    def cm(iterations=1):
        for i in range(iterations):
            t.cont(blocking=True)
            t.wait()

    def c():
        t.cont()

    def s():
        t.step()

    def d(addr=None, width=8):
        if addr is None:
            addr = t.read_register('pc')
        # noinspection PyUnresolvedReferences
        print(t.disassemble_pretty(addr=addr, insns=width))

    def dspc(width=8):
        values_on_stack = t.read_memory(t.read_register("sp"), 4, 8)
        m3_stack_regs = arch.REGISTERS_ON_STACK
        faulting_context = {m3_stack_regs[i]: values_on_stack[i] for i in range(len(m3_stack_regs))}
        # noinspection PyUnresolvedReferences
        print(t.disassemble_pretty(addr=faulting_context['pc'], insns=width))

    if hasattr(t, 'pretty_dump'):
        pretty: CortexM3DumpTool = t.pretty_dump

    def nvic():
        pretty.dump_nvic_info()

    def stack(offset=0):
        pretty.dump_stack(offset=offset)

    try:
        import IPython
        IPython.embed()
    except:
        print("Ipython issue")
