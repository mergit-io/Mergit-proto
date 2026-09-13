"""Mergit chain layer — real EVM proof-of-work.

Runs against an in-process EVM by default (no keys, no network, no tokens) and against
Monad testnet when an RPC URL and funded key are supplied. See
`docs/superpowers/specs/2026-08-12-onchain-proof-layer.md`.
"""
