// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Roles.sol";

/// @title AuditTrail
/// @notice Append-only audit log of agent tool invocations. Events only — zero SSTORE.
/// @dev PRD §5.2: the backend records what it actually invoked, never the LLM's claim about it.
///      Storing nothing keeps per-call gas at the floor; history lives in the event log.
contract AuditTrail is Roles {
    bytes32 public constant WRITER_ROLE = keccak256("WRITER_ROLE");

    event ActionLogged(
        uint256 indexed agentTokenId,
        string toolName,
        bytes32 argsHash,
        bytes32 resultHash,
        uint256 blockNumber
    );

    constructor(address admin) Roles(admin) {
        _grant(WRITER_ROLE, admin);
    }

    function logAction(
        uint256 agentTokenId,
        string calldata toolName,
        bytes32 argsHash,
        bytes32 resultHash
    ) external onlyRole(WRITER_ROLE) {
        emit ActionLogged(agentTokenId, toolName, argsHash, resultHash, block.number);
    }

    /// @notice Batch variant — one transaction for a whole task's tool calls.
    function logActions(
        uint256 agentTokenId,
        string[] calldata toolNames,
        bytes32[] calldata argsHashes,
        bytes32[] calldata resultHashes
    ) external onlyRole(WRITER_ROLE) {
        uint256 n = toolNames.length;
        require(n == argsHashes.length && n == resultHashes.length, "length mismatch");
        for (uint256 i = 0; i < n; ++i) {
            emit ActionLogged(agentTokenId, toolNames[i], argsHashes[i], resultHashes[i], block.number);
        }
    }
}
