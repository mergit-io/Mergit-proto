// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Roles.sol";

/// @title ReputationRegistry
/// @notice Oracle-updated composite reputation scores, 0..10000 (PRD §5.5 scale).
/// @dev The 20% max-delta anti-manipulation rule is enforced here in bytecode, not in the
///      off-chain service — a compromised oracle still cannot move a score arbitrarily.
///      `componentHash` binds the integer to the off-chain breakdown JSON so anyone can verify it.
contract ReputationRegistry is Roles {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    uint32 public constant MAX_SCORE = 10000;
    uint256 public constant MAX_DELTA_BPS = 2000; // 20%

    struct Score {
        uint32 score;
        bytes32 componentHash;
        uint64 updatedAt;
        uint32 updateCount;
    }

    mapping(uint256 => Score) private _scores;

    error ScoreOutOfRange(uint32 score);
    error DeltaTooLarge(uint32 oldScore, uint32 newScore, uint256 maxDelta);

    event ScoreUpdated(
        uint256 indexed agentTokenId, uint32 oldScore, uint32 newScore, bytes32 componentHash
    );

    constructor(address admin) Roles(admin) {
        _grant(ORACLE_ROLE, admin);
    }

    function updateScore(uint256 agentTokenId, uint32 newScore, bytes32 componentHash)
        external
        onlyRole(ORACLE_ROLE)
    {
        if (newScore > MAX_SCORE) revert ScoreOutOfRange(newScore);

        Score storage s = _scores[agentTokenId];
        uint32 oldScore = s.score;

        // The cap only applies once a non-zero score exists — the first write is unconstrained.
        if (s.updateCount > 0 && oldScore > 0) {
            uint256 maxDelta = (uint256(oldScore) * MAX_DELTA_BPS) / 10000;
            uint256 diff = newScore > oldScore
                ? uint256(newScore) - uint256(oldScore)
                : uint256(oldScore) - uint256(newScore);
            if (diff > maxDelta) revert DeltaTooLarge(oldScore, newScore, maxDelta);
        }

        s.score = newScore;
        s.componentHash = componentHash;
        s.updatedAt = uint64(block.timestamp);
        unchecked {
            s.updateCount += 1;
        }

        emit ScoreUpdated(agentTokenId, oldScore, newScore, componentHash);
    }

    function getScore(uint256 agentTokenId) external view returns (Score memory) {
        return _scores[agentTokenId];
    }

    /// @notice True when the supplied breakdown hash matches what the oracle committed on-chain.
    function verifyComponents(uint256 agentTokenId, bytes32 expectedComponentHash)
        external
        view
        returns (bool)
    {
        Score storage s = _scores[agentTokenId];
        return s.updateCount > 0 && s.componentHash == expectedComponentHash;
    }
}
