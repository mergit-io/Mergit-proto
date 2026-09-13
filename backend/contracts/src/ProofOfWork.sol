// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Roles.sol";

interface IAgentPassport {
    function exists(uint256 tokenId) external view returns (bool);
    function recordTaskResult(uint256 tokenId, bool success) external;
}

/// @title ProofOfWork
/// @notice Tamper-proof ledger of agent task results. One proof per task, forever.
/// @dev PRD §5.4 and Problem 1. `resultHash` is SHA-256 of the canonical JSON output, computed
///      off-chain by `economy.result_hash`. Anyone can recompute it and compare against `getProof`.
contract ProofOfWork is Roles {
    bytes32 public constant RECORDER_ROLE = keccak256("RECORDER_ROLE");

    struct Proof {
        bytes32 taskId;
        uint256 agentTokenId;
        bytes32 resultHash;
        uint64 recordedAt;
        uint64 blockNumber;
    }

    IAgentPassport public immutable passport;

    uint256 public proofCount;
    mapping(bytes32 => Proof) private _proofs;

    error ProofAlreadyRecorded(bytes32 taskId);
    error UnknownAgent(uint256 agentTokenId);
    error EmptyHash();

    event ProofRecorded(
        bytes32 indexed taskId,
        uint256 indexed agentTokenId,
        bytes32 resultHash,
        uint256 blockNumber
    );

    constructor(address admin, address passport_) Roles(admin) {
        if (passport_ == address(0)) revert ZeroAddress();
        passport = IAgentPassport(passport_);
        _grant(RECORDER_ROLE, admin);
    }

    /// @notice Record a task result. Idempotent by revert — a task is provable exactly once.
    function recordProof(bytes32 taskId, uint256 agentTokenId, bytes32 resultHash)
        external
        onlyRole(RECORDER_ROLE)
    {
        if (taskId == bytes32(0) || resultHash == bytes32(0)) revert EmptyHash();
        if (_proofs[taskId].taskId != bytes32(0)) revert ProofAlreadyRecorded(taskId);
        if (!passport.exists(agentTokenId)) revert UnknownAgent(agentTokenId);

        _proofs[taskId] = Proof({
            taskId: taskId,
            agentTokenId: agentTokenId,
            resultHash: resultHash,
            recordedAt: uint64(block.timestamp),
            blockNumber: uint64(block.number)
        });
        unchecked {
            proofCount += 1;
        }

        emit ProofRecorded(taskId, agentTokenId, resultHash, block.number);
        passport.recordTaskResult(agentTokenId, true);
    }

    /// @notice Returns a zeroed Proof when the task was never recorded — callers check `taskId`.
    function getProof(bytes32 taskId) external view returns (Proof memory) {
        return _proofs[taskId];
    }

    function isRecorded(bytes32 taskId) external view returns (bool) {
        return _proofs[taskId].taskId != bytes32(0);
    }

    /// @notice Convenience for verifiers: does the chain agree with a locally computed hash?
    function verify(bytes32 taskId, bytes32 expectedResultHash) external view returns (bool) {
        Proof storage p = _proofs[taskId];
        return p.taskId != bytes32(0) && p.resultHash == expectedResultHash;
    }
}
