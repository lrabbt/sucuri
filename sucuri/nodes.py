# Sucuri - Minimalistic Python Dataflow Programming Library
# author: tiago@ime.uerj.br
from .pydf import *
import bisect
import itertools


class TaggedValue:
    def __init__(self, value, tag):
        self.value = value
        self.tag = tag
        self.request_task = True

    def __repr__(self):
        return "TaggedValue: (%d, %s)" % (self.tag, self.value)

    def __eq__(self, other):
        if other is not None and not isinstance(other, TaggedValue):
            raise TypeError("Can only compare TaggedValue with TaggedValue.")
        return other is not None and self.tag == other.tag

    def __lt__(self, other):
        if other is None:
            return False
        if not isinstance(other, TaggedValue):
            raise TypeError("Can only compare TaggedValue with TaggedValue.")
        return self.tag < other.tag


class Source(Node):
    def __init__(self, it):
        self.it = it
        self.inport = []
        self.dsts = []
        self.tagcounter = 0

        self.affinity = None

    def run(self, args, workerid, operq):
        for line in self.it:
            result = self.f(line, args)

            tag = self.tagcounter
            opers = self.create_oper(TaggedValue(result, tag), workerid, operq)
            for oper in opers:
                oper.request_task = False
            self.sendops(opers, operq)
            self.tagcounter += 1
        # sinalize eof and request a task
        opers = [Oper(workerid, None, None, None)]
        self.sendops(opers, operq)

    def f(self, line, args):
        """Default source operation"""
        return line


class FlipFlop(Node):
    def __init__(self, f):
        self.f = f
        self.inport = [[], []]
        self.dsts = []
        self.affinity = None

    def run(self, args, workerid, operq):
        opers = self.create_oper(self.f([a.val for a in args]), workerid, operq)

        if opers[0].val == False:
            opers = [Oper(workerid, None, None, None)]
        self.sendops(opers, operq)


class FilterTagged(Node):
    """Produce operands in the form of TaggedValue, with the same tag as the input"""

    def run(self, args, workerid, operq):
        if args[0] is None:
            opers = [Oper(workerid, None, None, None)]
            self.sendops(opers, operq)
            return 0
        tag = args[0].val.tag
        argvalues = [arg.val.value for arg in args]
        result = self.f(argvalues)
        opers = self.create_oper(TaggedValue(result, tag), workerid, operq)
        self.sendops(opers, operq)


class Feeder(Node):
    def __init__(self, value):
        self.value = value
        self.dsts = []
        self.inport = []
        self.affinity = None
        print("Setting feeder affinity")

    def f(self):
        return self.value


class Serializer(Node):
    def __init__(self, f, inputn):
        Node.__init__(self, f, inputn)
        self.serial_buffer = []
        self.next_tag = 0
        self.arg_buffer = [[] for i in range(inputn)]
        self.f = f
        # Default affinity to Worker-0 (Serializer HAS to be pinned)
        self.affinity = [0]

    def run(self, args, workerid, operq):
        if args[0] is None:
            opers = [Oper(workerid, None, None, None)]
            self.sendops(opers, operq)
            return 0

        for arg, argbuffer in itertools.zip_longest(args, self.arg_buffer):
            bisect.insort(argbuffer, arg.val)
        if args[0].val.tag == self.next_tag:
            next = self.next_tag
            argbuffer = self.arg_buffer
            buffertag = argbuffer[0][0].tag
            while buffertag == next:
                args = [arg.pop(0) for arg in argbuffer]
                print("Sending oper with tag %d" % args[0].tag)
                opers = self.create_oper(
                    self.f([arg.value for arg in args]), workerid, operq
                )
                self.sendops(opers, operq)
                next += 1
                if len(argbuffer[0]) > 0:
                    buffertag = argbuffer[0][0].tag
                else:
                    buffertag = None

            self.next_tag = next
