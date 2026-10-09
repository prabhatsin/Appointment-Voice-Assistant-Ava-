
#! Step 1: Networking fundamentals
'''
First, understand these four concepts:
1. IP address — identifies a device or network interface.
2. Port — identifies a particular service or application endpoint on a device.
3. Client-server model — how two applications communicate.

4. Packets — how data travels across a network.

'''

#? Packets



'''
A network packet is a small, formatted unit of data created by breaking down a larger message so it can 
travel efficiently across a computer network


Structure of a Packet

A standard network packet contains three main parts:

1: Header: Control information at the start that tells the network where the packet came from (sender IP), 
where it is going (receiver IP), how long it should live, and its sequence number(not needed in udp)

NOTE:Important correction: A sequence number is not a standard IPv4 header field. TCP has sequence numbers
in its own header, while UDP does not.

2:The actual chunk of user data (like a piece of a photo, text message, or video file) being transported.

    For example, in our Voice AI project, a UDP datagram's payload might contain RTP packets carrying encoded Opus audio.

3:Trailer (or Footer): Extra bits at the end that signal the finish line and use error-checking codes 
(like a checksum) to make sure the data did not get corrupted during the trip

'''

#!Step2 
