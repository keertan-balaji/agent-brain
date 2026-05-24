"""Provenance behavior is covered indirectly by test_write_generation_depth.py.

The plan lists this file but provides no test bodies — provenance_kind
('captured' / 'ingested' / 'synthesized' / 'user_authored') is exercised
through the generation_depth tests, where 'synthesized' triggers depth
computation and the other kinds default to depth 0. Kept as an empty
placeholder so the spec's file list is complete.
"""
