// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PassportAnchor
/// @notice Polygon Amoy record for a BTU passport version.
///         Stores two fingerprints only. Callers must not pass names, emails, or skill text.
contract PassportAnchor {
    address public immutable issuer;

    mapping(bytes32 verificationIdHash => bytes32 contentHash) public anchors;

    event Anchored(bytes32 indexed contentHash, bytes32 indexed verificationIdHash);

    error NotIssuer();
    error AlreadyAnchored();

    constructor() {
        issuer = msg.sender;
    }

    function anchor(bytes32 contentHash, bytes32 verificationIdHash) external {
        if (msg.sender != issuer) revert NotIssuer();
        if (anchors[verificationIdHash] != bytes32(0)) revert AlreadyAnchored();
        anchors[verificationIdHash] = contentHash;
        emit Anchored(contentHash, verificationIdHash);
    }
}
