// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Roles.sol";

/// @title AgentPassport
/// @notice Soulbound identity token for a Mergit agent. One per address, non-transferable.
/// @dev PRD §5.3. Task counters are advanced by ProofOfWork, which holds RECORDER_ROLE.
contract AgentPassport is Roles {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant RECORDER_ROLE = keccak256("RECORDER_ROLE");

    string public constant name = "Mergit Agent Passport";
    string public constant symbol = "MAP";

    struct Passport {
        uint256 tokenId;
        address owner;
        string did;
        bytes32 capabilityHash;
        uint64 tasksCompleted;
        uint64 tasksAttempted;
        uint64 registeredAt;
        bool active;
    }

    uint256 public totalSupply;

    mapping(uint256 => Passport) private _passports;
    /// @notice 0 means "no passport" — token ids start at 1.
    mapping(address => uint256) public agentToTokenId;

    error Soulbound();
    error AlreadyMinted(address agent);
    error UnknownToken(uint256 tokenId);

    event PassportMinted(
        uint256 indexed tokenId, address indexed owner, string did, bytes32 capabilityHash
    );
    event TaskResultRecorded(
        uint256 indexed tokenId, bool success, uint64 tasksCompleted, uint64 tasksAttempted
    );
    event ActiveSet(uint256 indexed tokenId, bool active);

    constructor(address admin) Roles(admin) {
        _grant(MINTER_ROLE, admin);
    }

    function mint(address owner_, string calldata did, bytes32 capabilityHash)
        external
        onlyRole(MINTER_ROLE)
        returns (uint256)
    {
        if (owner_ == address(0)) revert ZeroAddress();
        if (agentToTokenId[owner_] != 0) revert AlreadyMinted(owner_);

        uint256 tokenId = ++totalSupply;
        _passports[tokenId] = Passport({
            tokenId: tokenId,
            owner: owner_,
            did: did,
            capabilityHash: capabilityHash,
            tasksCompleted: 0,
            tasksAttempted: 0,
            registeredAt: uint64(block.timestamp),
            active: true
        });
        agentToTokenId[owner_] = tokenId;

        emit PassportMinted(tokenId, owner_, did, capabilityHash);
        return tokenId;
    }

    function recordTaskResult(uint256 tokenId, bool success) external onlyRole(RECORDER_ROLE) {
        Passport storage p = _passports[tokenId];
        if (p.tokenId == 0) revert UnknownToken(tokenId);

        unchecked {
            p.tasksAttempted += 1;
            if (success) p.tasksCompleted += 1;
        }
        emit TaskResultRecorded(tokenId, success, p.tasksCompleted, p.tasksAttempted);
    }

    function setActive(uint256 tokenId, bool active) external onlyRole(DEFAULT_ADMIN_ROLE) {
        Passport storage p = _passports[tokenId];
        if (p.tokenId == 0) revert UnknownToken(tokenId);
        p.active = active;
        emit ActiveSet(tokenId, active);
    }

    // ── Views ───────────────────────────────────────────────────────────────────

    function getPassport(uint256 tokenId) external view returns (Passport memory) {
        Passport memory p = _passports[tokenId];
        if (p.tokenId == 0) revert UnknownToken(tokenId);
        return p;
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        Passport storage p = _passports[tokenId];
        if (p.tokenId == 0) revert UnknownToken(tokenId);
        return p.owner;
    }

    function balanceOf(address account) external view returns (uint256) {
        return agentToTokenId[account] == 0 ? 0 : 1;
    }

    function exists(uint256 tokenId) external view returns (bool) {
        return _passports[tokenId].tokenId != 0;
    }

    // ── Soulbound: every transfer/approval path reverts ─────────────────────────

    function transferFrom(address, address, uint256) external pure {
        revert Soulbound();
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert Soulbound();
    }

    function safeTransferFrom(address, address, uint256, bytes calldata) external pure {
        revert Soulbound();
    }

    function approve(address, uint256) external pure {
        revert Soulbound();
    }

    function setApprovalForAll(address, bool) external pure {
        revert Soulbound();
    }
}
