// The A25's data memory in the core (DLM, 0xA0200000): its size as the IP generator writes it
// (codes 12 to 16, smallest first; 13 is the fpc console's: sw/link.ld uses 32 KB of it)

`define DTCM_SIZE 13
