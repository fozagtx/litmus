"""
Benchmark Case Generator & Populator.
Generates the 16 realistic, diverse smart contract security benchmark cases.
"""

import json
from pathlib import Path

CASES = [
    {
        "case_id": "case_01",
        "title": "EtherVault Reentrancy Drain",
        "category": "Reentrancy",
        "difficulty": "Normal",
        "vulnerability_type": "REENTRANCY",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EtherVault {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 balance = balances[msg.sender];
        require(balance > 0, "No balance");

        (bool success, ) = msg.sender.call{value: balance}("");
        require(success, "Transfer failed");

        balances[msg.sender] = 0;
    }
}""",
        "vulnerability_description": "EtherVault updates balances[msg.sender] AFTER sending ether to msg.sender via low-level call, violating Checks-Effects-Interactions and allowing recursive withdrawal drain.",
        "exploit_poc": """contract Attacker {
    EtherVault public vault;
    constructor(address _vault) { vault = EtherVault(_vault); }
    receive() external payable {
        if (address(vault).balance >= 1 ether) { vault.withdraw(); }
    }
    function attack() external payable {
        vault.deposit{value: 1 ether}();
        vault.withdraw();
    }
}""",
        "invariants": [
            "Solvency: sum(balances) <= address(this).balance",
            "Legitimate user withdrawal: users can withdraw their deposited balance"
        ],
        "regression_tests": [
            {"name": "Legitimate Deposit and Withdraw", "description": "User deposits 1 ether and withdraws 1 ether", "function_called": "withdraw", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Must retain withdraw() and deposit() interface", "Gas efficient"],
        "baseline_failure_mode": "Baseline often adds reentrancy lock without updating balance before call, or deletes transfer, breaking legitimate withdrawals.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EtherVault {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 balance = balances[msg.sender];
        require(balance > 0, "No balance");

        balances[msg.sender] = 0;

        (bool success, ) = msg.sender.call{value: balance}("");
        require(success, "Transfer failed");
    }
}"""
    },
    {
        "case_id": "case_02",
        "title": "ERC4626 Vault Inflation Attack",
        "category": "DeFi / Rounding",
        "difficulty": "Difficult",
        "vulnerability_type": "VAULT_INFLATION",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleVault {
    mapping(address => uint256) public shares;
    uint256 public totalShares;
    uint256 public totalAssets;

    function deposit(uint256 assets) external returns (uint256) {
        require(assets > 0, "Zero assets");
        uint256 mintShares;
        if (totalShares == 0) {
            mintShares = assets;
        } else {
            mintShares = (assets * totalShares) / totalAssets;
        }
        require(mintShares > 0, "Zero shares minted");
        shares[msg.sender] += mintShares;
        totalShares += mintShares;
        totalAssets += assets;
        return mintShares;
    }

    function redeem(uint256 shareAmount) external returns (uint256) {
        require(shares[msg.sender] >= shareAmount, "Insufficient shares");
        uint256 assetAmount = (shareAmount * totalAssets) / totalShares;
        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalAssets -= assetAmount;
        return assetAmount;
    }
}""",
        "vulnerability_description": "First depositor can mint 1 share, donate large assets to inflate totalAssets / totalShares, causing subsequent victim deposits to round down to 0 shares and lose funds upon attacker redemption.",
        "exploit_poc": """// Attacker deposits 1 wei, donates 100e18 assets directly to inflate share price.
// Victim deposits 50e18 assets -> shares = (50e18 * 1) / 100e18 = 0 shares minted. Attacker steals victim funds.""",
        "invariants": [
            "Solvency: totalAssets >= sum(shares)",
            "Non-zero share allocation: non-trivial deposits receive fair proportional shares",
            "Legitimate user withdrawal possible"
        ],
        "regression_tests": [
            {"name": "Standard User Deposit", "description": "User deposits 100 assets", "function_called": "deposit", "caller": "0xUser1", "args": {"assets": 100}, "expected_success": True},
            {"name": "Standard User Redeem", "description": "User redeems shares", "function_called": "redeem", "caller": "0xUser1", "args": {"shareAmount": 100}, "expected_success": True}
        ],
        "constraints": ["Preserve ERC4626 style deposit/redeem interfaces", "Virtual offset or dead shares applied"],
        "baseline_failure_mode": "Baseline adds arbitrary require check or breaks share calculation without applying virtual offsets (e.g. + 1 or dead shares), causing division by zero or permanent user fund lock.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleVault {
    mapping(address => uint256) public shares;
    uint256 public totalShares;
    uint256 public totalAssets;

    function deposit(uint256 assets) external returns (uint256) {
        require(assets > 0, "Zero assets");
        uint256 mintShares;
        if (totalShares == 0) {
            mintShares = assets;
        } else {
            mintShares = (assets * (totalShares + 1e3)) / (totalAssets + 1);
        }
        require(mintShares > 0, "Zero shares minted");
        shares[msg.sender] += mintShares;
        totalShares += mintShares;
        totalAssets += assets;
        return mintShares;
    }

    function redeem(uint256 shareAmount) external returns (uint256) {
        require(shares[msg.sender] >= shareAmount, "Insufficient shares");
        uint256 assetAmount = (shareAmount * (totalAssets + 1)) / (totalShares + 1e3);
        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalAssets -= assetAmount;
        return assetAmount;
    }
}"""
    },
    {
        "case_id": "case_03",
        "title": "Missing Access Control on Admin Treasury Withdrawal",
        "category": "Access Control",
        "difficulty": "Normal",
        "vulnerability_type": "ACCESS_CONTROL",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Treasury {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function withdrawAdmin(address to, uint256 amount) external {
        require(address(this).balance >= amount, "Insufficient treasury");
        (bool success, ) = to.call{value: amount}("");
        require(success, "Transfer failed");
    }

    receive() external payable {}
}""",
        "vulnerability_description": "withdrawAdmin is public/external with no modifier or authorization check, permitting any attacker to drain treasury funds.",
        "exploit_poc": """Attacker calls Treasury.withdrawAdmin(attackerAddress, address(treasury).balance) directly without being owner.""",
        "invariants": [
            "Admin boundary: only authorized owner can withdraw treasury funds",
            "No unauthorized drain"
        ],
        "regression_tests": [
            {"name": "Owner Withdraw", "description": "Owner initiates admin withdrawal", "function_called": "withdrawAdmin", "caller": "0xOwner", "args": {"to": "0xOwner", "amount": 10}, "expected_success": True}
        ],
        "constraints": ["Must keep withdrawAdmin signature", "Require msg.sender == owner check or onlyOwner modifier"],
        "baseline_failure_mode": "Baseline often removes the function entirely or changes function signature, breaking caller contracts.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Treasury {
    address public owner;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function withdrawAdmin(address to, uint256 amount) external onlyOwner {
        require(address(this).balance >= amount, "Insufficient treasury");
        (bool success, ) = to.call{value: amount}("");
        require(success, "Transfer failed");
    }

    receive() external payable {}
}"""
    },
    {
        "case_id": "case_04",
        "title": "Oracle Staleness & Incomplete Round Validation",
        "category": "Oracles",
        "difficulty": "Difficult",
        "vulnerability_type": "ORACLE_STALENESS",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IAggregatorV3 {
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

contract PriceConsumer {
    IAggregatorV3 public priceFeed;

    constructor(address _feed) {
        priceFeed = IAggregatorV3(_feed);
    }

    function getLatestPrice() public view returns (uint256) {
        (, int256 price, , , ) = priceFeed.latestRoundData();
        require(price > 0, "Invalid price");
        return uint256(price);
    }
}""",
        "vulnerability_description": "getLatestPrice ignores round completeness (answeredInRound < roundId) and timestamp freshness (updatedAt stale), allowing exploitation during oracle stalls.",
        "exploit_poc": """Oracle sequencer stalls, price remains frozen from 3 days ago. Attacker executes liquidation/borrowing arbitrage at stale price.""",
        "invariants": [
            "Price Freshness: updatedAt must be within max staleness threshold (e.g. 3600 seconds)",
            "Round Completeness: answeredInRound >= roundId"
        ],
        "regression_tests": [
            {"name": "Valid Fresh Price Query", "description": "Fetches active valid price", "function_called": "getLatestPrice", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Validate updatedAt > 0 and answeredInRound >= roundId and block.timestamp - updatedAt <= 3600"],
        "baseline_failure_mode": "Baseline forgets answeredInRound check or hardcodes fixed block number causing compilation issues.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IAggregatorV3 {
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

contract PriceConsumer {
    IAggregatorV3 public priceFeed;
    uint256 public constant MAX_STALENESS = 3600;

    constructor(address _feed) {
        priceFeed = IAggregatorV3(_feed);
    }

    function getLatestPrice() public view returns (uint256) {
        (uint80 roundId, int256 price, , uint256 updatedAt, uint80 answeredInRound) = priceFeed.latestRoundData();
        require(price > 0, "Invalid price");
        require(updatedAt > 0, "Round incomplete");
        require(answeredInRound >= roundId, "Stale round data");
        require(block.timestamp - updatedAt <= MAX_STALENESS, "Price data too stale");
        return uint256(price);
    }
}"""
    },
    {
        "case_id": "case_05",
        "title": "Signature Replay & Missing Nonce Invalidation",
        "category": "Cryptography",
        "difficulty": "Normal",
        "vulnerability_type": "SIGNATURE_REPLAY",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleAirdrop {
    address public signer;

    constructor(address _signer) {
        signer = _signer;
    }

    function claim(address recipient, uint256 amount, bytes32 r, bytes32 s, uint8 v) external {
        bytes32 messageHash = keccak256(abi.encodePacked(recipient, amount));
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\\x19Ethereum Signed Message:\\n32", messageHash));

        address recovered = ecrecover(ethSignedMessageHash, v, r, s);
        require(recovered == signer, "Invalid signature");

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "Payout failed");
    }
}""",
        "vulnerability_description": "claim() verifies valid signature but does not track nonce or mark the signature hash as consumed, permitting the recipient or any relayer to replay the signature indefinitely.",
        "exploit_poc": """Attacker receives 1 valid signature for 1 ether airdrop and loops claim() 100 times to drain contract balance.""",
        "invariants": [
            "Single-use signature authorization: each nonce/signature can only be claimed once",
            "Balance conservation"
        ],
        "regression_tests": [
            {"name": "First Valid Claim", "description": "User claims valid airdrop", "function_called": "claim", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Include mapping(address => uint256) public nonces or mapping(bytes32 => bool) public executed"],
        "baseline_failure_mode": "Baseline adds nonce to function arguments without incrementing or checking storage state.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleAirdrop {
    address public signer;
    mapping(bytes32 => bool) public usedSignatures;

    constructor(address _signer) {
        signer = _signer;
    }

    function claim(address recipient, uint256 amount, bytes32 r, bytes32 s, uint8 v) external {
        bytes32 messageHash = keccak256(abi.encodePacked(recipient, amount));
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\\x19Ethereum Signed Message:\\n32", messageHash));

        require(!usedSignatures[ethSignedMessageHash], "Signature already used");

        address recovered = ecrecover(ethSignedMessageHash, v, r, s);
        require(recovered == signer, "Invalid signature");

        usedSignatures[ethSignedMessageHash] = true;

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "Payout failed");
    }
}"""
    },
    {
        "case_id": "case_06",
        "title": "Precision Loss via Division Before Multiplication",
        "category": "Arithmetic",
        "difficulty": "Normal",
        "vulnerability_type": "PRECISION_LOSS",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract FeeDistributor {
    uint256 public feeBasisPoints = 250; // 2.5%
    uint256 public constant BPS_DENOMINATOR = 10000;

    function calculateFee(uint256 amount) public view returns (uint256) {
        // Bug: amount / BPS_DENOMINATOR rounds down to 0 for any amount < 10000
        uint256 unitFee = amount / BPS_DENOMINATOR;
        return unitFee * feeBasisPoints;
    }

    function processPayment(uint256 amount) external payable returns (uint256 fee) {
        fee = calculateFee(amount);
        return fee;
    }
}""",
        "vulnerability_description": "amount / BPS_DENOMINATOR truncates to zero for amounts under 10000, allowing users to make small transfers and completely evade protocol fees.",
        "exploit_poc": """Attacker splits a 1,000,000 token transaction into 100 transactions of 9,999 tokens. Fee charged on each is (9999 / 10000) * 250 = 0 tokens.""",
        "invariants": [
            "Strict Non-Negative Fee Proportionality: fee == (amount * feeBasisPoints) / BPS_DENOMINATOR",
            "Zero evasion on sub-10000 amounts"
        ],
        "regression_tests": [
            {"name": "Standard Fee Calculation", "description": "Calculate fee for 100,000 amount", "function_called": "calculateFee", "caller": "0xUser1", "args": {"amount": 100000}, "expected_success": True}
        ],
        "constraints": ["Multiply first before dividing: (amount * feeBasisPoints) / BPS_DENOMINATOR"],
        "baseline_failure_mode": "Baseline attempts floating point conversions or introduces off-by-one errors.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract FeeDistributor {
    uint256 public feeBasisPoints = 250; // 2.5%
    uint256 public constant BPS_DENOMINATOR = 10000;

    function calculateFee(uint256 amount) public view returns (uint256) {
        return (amount * feeBasisPoints) / BPS_DENOMINATOR;
    }

    function processPayment(uint256 amount) external payable returns (uint256 fee) {
        fee = calculateFee(amount);
        return fee;
    }
}"""
    },
    {
        "case_id": "case_07",
        "title": "Unchecked Low-Level Call Return Value",
        "category": "Error Handling",
        "difficulty": "Normal",
        "vulnerability_type": "UNCHECKED_CALL",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract RewardPool {
    mapping(address => uint256) public rewards;

    function setReward(address user, uint256 amount) external {
        rewards[user] = amount;
    }

    function claimReward() external {
        uint256 amount = rewards[msg.sender];
        require(amount > 0, "No reward");

        rewards[msg.sender] = 0;

        // Unchecked call return value
        msg.sender.call{value: amount}("");
    }
}""",
        "vulnerability_description": "msg.sender.call{value: amount}(\"\") does not validate return success bool. If call fails or reverts, user balance is wiped to 0 with zero ether delivered.",
        "exploit_poc": """Smart contract wallet with gas-restricted fallback attempts withdrawal; call fails silently, contract zeros out reward without paying user.""",
        "invariants": [
            "Atomic state transition: rewards only deducted if transfer succeeds",
            "Solvency"
        ],
        "regression_tests": [
            {"name": "Valid Reward Claim", "description": "User claims available reward", "function_called": "claimReward", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Check (bool success, ) = msg.sender.call... and require(success, ...)"],
        "baseline_failure_mode": "Baseline reverts the order back to CEI violation or replaces with deprecated transfer().",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract RewardPool {
    mapping(address => uint256) public rewards;

    function setReward(address user, uint256 amount) external {
        rewards[user] = amount;
    }

    function claimReward() external {
        uint256 amount = rewards[msg.sender];
        require(amount > 0, "No reward");

        rewards[msg.sender] = 0;

        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
    }
}"""
    },
    {
        "case_id": "case_08",
        "title": "Flash Loan Callback Reentrancy",
        "category": "Flash Loans",
        "difficulty": "Difficult",
        "vulnerability_type": "REENTRANCY",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IFlashBorrower {
    function onFlashLoan(uint256 amount, uint256 fee) external returns (bytes32);
}

contract FlashLender {
    uint256 public poolBalance;
    uint256 public constant FEE_BPS = 10; // 0.1%

    function deposit() external payable {
        poolBalance += msg.value;
    }

    function flashLoan(address receiver, uint256 amount) external {
        require(amount <= poolBalance, "Exceeds pool balance");
        uint256 fee = (amount * FEE_BPS) / 10000;
        uint256 balanceBefore = poolBalance;

        // Callback before balance check
        (bool success, ) = receiver.call{value: amount}("");
        require(success, "Transfer failed");

        bytes32 callbackResult = IFlashBorrower(receiver).onFlashLoan(amount, fee);
        require(callbackResult == keccak256("IFlashBorrower.onFlashLoan"), "Invalid callback");

        require(address(this).balance >= balanceBefore + fee, "Flash loan not repaid");
        poolBalance = address(this).balance;
    }
}""",
        "vulnerability_description": "flashLoan lacks nonReentrant guard, allowing the borrower inside onFlashLoan() callback to initiate nested flash loans or drain operations before repayment validation.",
        "exploit_poc": """Borrower re-enters flashLoan or withdraw during callback to manipulate repayment checks and extract pool assets.""",
        "invariants": [
            "Non-reentrancy on loan execution",
            "Pool balance monotonically increases by fee on each loan"
        ],
        "regression_tests": [
            {"name": "Standard Flash Loan Execution", "description": "Honest borrower takes and repays flash loan", "function_called": "flashLoan", "caller": "0xBorrower", "args": {"amount": 100}, "expected_success": True}
        ],
        "constraints": ["Add nonReentrant guard or explicit reentrancy lock"],
        "baseline_failure_mode": "Baseline creates lock that never gets cleared or removes the callback functionality entirely.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IFlashBorrower {
    function onFlashLoan(uint256 amount, uint256 fee) external returns (bytes32);
}

contract FlashLender {
    uint256 public poolBalance;
    uint256 public constant FEE_BPS = 10;
    bool private _locked;

    modifier nonReentrant() {
        require(!_locked, "Reentrant call");
        _locked = true;
        _;
        _locked = false;
    }

    function deposit() external payable {
        poolBalance += msg.value;
    }

    function flashLoan(address receiver, uint256 amount) external nonReentrant {
        require(amount <= poolBalance, "Exceeds pool balance");
        uint256 fee = (amount * FEE_BPS) / 10000;
        uint256 balanceBefore = poolBalance;

        (bool success, ) = receiver.call{value: amount}("");
        require(success, "Transfer failed");

        bytes32 callbackResult = IFlashBorrower(receiver).onFlashLoan(amount, fee);
        require(callbackResult == keccak256("IFlashBorrower.onFlashLoan"), "Invalid callback");

        require(address(this).balance >= balanceBefore + fee, "Flash loan not repaid");
        poolBalance = address(this).balance;
    }
}"""
    },
    {
        "case_id": "case_09",
        "title": "Arbitrary Delegatecall to Untrusted Target",
        "category": "Delegatecall",
        "difficulty": "Difficult",
        "vulnerability_type": "ARBITRARY_DELEGATECALL",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MultiCaller {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function execute(address target, bytes calldata data) external returns (bytes memory) {
        // Arbitrary delegatecall allows user-supplied target to overwrite owner slot in MultiCaller storage
        (bool success, bytes memory result) = target.delegatecall(data);
        require(success, "Delegatecall failed");
        return result;
    }
}""",
        "vulnerability_description": "execute() executes delegatecall to arbitrary caller-supplied address, allowing attacker to supply a malicious contract that overwrites slot 0 (owner) or executes selfdestruct.",
        "exploit_poc": """Attacker deploys ExploitContract with storage layout matching MultiCaller, calls execute(exploit, setOwnerData) and hijacks contract ownership.""",
        "invariants": [
            "Storage integrity: only whitelisted implementations can be invoked via delegatecall",
            "Owner storage slot cannot be modified by arbitrary callers"
        ],
        "regression_tests": [
            {"name": "Owner Whitelisted Execution", "description": "Execute approved logic", "function_called": "execute", "caller": "0xOwner", "args": {}, "expected_success": True}
        ],
        "constraints": ["Add mapping(address => bool) public allowedTargets with onlyOwner configuration"],
        "baseline_failure_mode": "Baseline changes delegatecall to regular call without preserving return types or breaking caller interfaces.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MultiCaller {
    address public owner;
    mapping(address => bool) public allowedTargets;

    modifier onlyOwner() {
        require(msg.sender == owner, "Unauthorized");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function setAllowedTarget(address target, bool allowed) external onlyOwner {
        allowedTargets[target] = allowed;
    }

    function execute(address target, bytes calldata data) external returns (bytes memory) {
        require(allowedTargets[target], "Target not allowed");
        (bool success, bytes memory result) = target.delegatecall(data);
        require(success, "Delegatecall failed");
        return result;
    }
}"""
    },
    {
        "case_id": "case_10",
        "title": "ERC20 Fee-on-Transfer Invariant Accounting Mismatch",
        "category": "ERC20 Accounting",
        "difficulty": "Difficult",
        "vulnerability_type": "FEE_ON_TRANSFER",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract StakingPool {
    IERC20 public stakingToken;
    mapping(address => uint256) public balances;
    uint256 public totalStaked;

    constructor(address _token) {
        stakingToken = IERC20(_token);
    }

    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount");
        // Flaw: credits full amount even if token takes a fee on transfer
        stakingToken.transferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += amount;
        totalStaked += amount;
    }
}""",
        "vulnerability_description": "deposit() credits amount parameter to user balance without checking actual received balance differential. With fee-on-transfer tokens, contract becomes insolvent and cannot satisfy all withdrawals.",
        "exploit_poc": """Attacker deposits 100 fee-on-transfer tokens (contract receives 90 tokens, credits 100). Attacker later withdraws 100 tokens, stealing other users' funds.""",
        "invariants": [
            "Solvency: stakingToken.balanceOf(address(this)) >= totalStaked",
            "Credited amount equals actual balance delta"
        ],
        "regression_tests": [
            {"name": "Deposit Token", "description": "Deposit standard token", "function_called": "deposit", "caller": "0xUser1", "args": {"amount": 100}, "expected_success": True}
        ],
        "constraints": ["Calculate balance delta: balanceAfter - balanceBefore"],
        "baseline_failure_mode": "Baseline hallucinates a non-existent token interface or removes the transferFrom call.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract StakingPool {
    IERC20 public stakingToken;
    mapping(address => uint256) public balances;
    uint256 public totalStaked;

    constructor(address _token) {
        stakingToken = IERC20(_token);
    }

    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount");
        uint256 balanceBefore = stakingToken.balanceOf(address(this));
        stakingToken.transferFrom(msg.sender, address(this), amount);
        uint256 balanceAfter = stakingToken.balanceOf(address(this));
        uint256 actualReceived = balanceAfter - balanceBefore;
        require(actualReceived > 0, "No tokens received");

        balances[msg.sender] += actualReceived;
        totalStaked += actualReceived;
    }
}"""
    },
    {
        "case_id": "case_11",
        "title": "Uninitialized Proxy Logic Contract Owner",
        "category": "Upgradeable Proxies",
        "difficulty": "Normal",
        "vulnerability_type": "ACCESS_CONTROL",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract LogicV1 {
    address public owner;
    bool public initialized;

    function initialize(address _owner) external {
        require(!initialized, "Already initialized");
        initialized = true;
        owner = _owner;
    }

    function upgradeToAndCall(address newImplementation, bytes calldata data) external {
        require(msg.sender == owner, "Unauthorized");
        // upgrade logic...
    }
}""",
        "vulnerability_description": "Logic contract implementation is uninitialized upon deployment. Attacker can call initialize(attacker) on the logic contract directly and selfdestruct or compromise it.",
        "exploit_poc": """Attacker directly invokes LogicV1.initialize(attacker) on unproxied implementation contract, becoming owner.""",
        "invariants": [
            "Constructor locks logic implementation initialization",
            "Proxy caller can still initialize proxy instance once"
        ],
        "regression_tests": [
            {"name": "Proxy Initialization", "description": "Initialize proxy instance", "function_called": "initialize", "caller": "0xOwner", "args": {"_owner": "0xOwner"}, "expected_success": True}
        ],
        "constraints": ["Add constructor() { initialized = true; } or _disableInitializers()"],
        "baseline_failure_mode": "Baseline removes initialize function, preventing proxy instantiation.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract LogicV1 {
    address public owner;
    bool public initialized;

    constructor() {
        initialized = true;
    }

    function initialize(address _owner) external {
        require(!initialized, "Already initialized");
        initialized = true;
        owner = _owner;
    }

    function upgradeToAndCall(address newImplementation, bytes calldata data) external {
        require(msg.sender == owner, "Unauthorized");
    }
}"""
    },
    {
        "case_id": "case_12",
        "title": "Strict Balance Equality DoS",
        "category": "DoS",
        "difficulty": "Normal",
        "vulnerability_type": "STRICT_BALANCE_EQUALITY",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MilestoneGame {
    uint256 public constant TARGET_BALANCE = 10 ether;
    address public winner;

    function play() external payable {
        require(msg.value == 1 ether, "Must deposit 1 ether");
        // Strict equality check
        if (address(this).balance == TARGET_BALANCE) {
            winner = msg.sender;
        }
    }

    function claimPrize() external {
        require(msg.sender == winner, "Not winner");
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Failed");
    }
}""",
        "vulnerability_description": "Strict equality address(this).balance == TARGET_BALANCE can be permanently bricked by forcibly sending ether via selfdestruct or block reward, breaking game completion.",
        "exploit_poc": """Attacker uses selfdestruct to forcibly send 0.1 ether to MilestoneGame. balance will never equal exact integer TARGET_BALANCE.""",
        "invariants": [
            "Game progression is robust against forced ether donations",
            "address(this).balance >= TARGET_BALANCE condition"
        ],
        "regression_tests": [
            {"name": "Play Step", "description": "Deposit 1 ether", "function_called": "play", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Use >= comparison instead of =="],
        "baseline_failure_mode": "Baseline adds arbitrary require that prevents all deposits.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MilestoneGame {
    uint256 public constant TARGET_BALANCE = 10 ether;
    address public winner;

    function play() external payable {
        require(msg.value == 1 ether, "Must deposit 1 ether");
        if (address(this).balance >= TARGET_BALANCE && winner == address(0)) {
            winner = msg.sender;
        }
    }

    function claimPrize() external {
        require(msg.sender == winner, "Not winner");
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Failed");
    }
}"""
    },
    {
        "case_id": "case_13",
        "title": "Block Timestamp Manipulation in Lottery",
        "category": "Randomness",
        "difficulty": "Normal",
        "vulnerability_type": "TIMESTAMP_MANIPULATION",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TimestampLottery {
    address public winner;

    function draw() external {
        // Miner can manipulate block.timestamp by +/- 15 seconds to win
        require(block.timestamp % 15 == 0, "Not lucky time");
        winner = msg.sender;
    }
}""",
        "vulnerability_description": "Using block.timestamp for winning conditions allows miners/validators to manipulate block timestamps to satisfy the condition.",
        "exploit_poc": """Miner sets timestamp = 1700000005 (divisible by 15) to guarantee winning transaction included in their mined block.""",
        "invariants": [
            "Fair winner selection not dependent on validator timestamp malleability",
            "Predictable verifiable state transition"
        ],
        "regression_tests": [
            {"name": "Draw Lottery", "description": "Execute draw flow", "function_called": "draw", "caller": "0xUser1", "args": {}, "expected_success": True}
        ],
        "constraints": ["Replace modular timestamp check with secure commit-reveal or verifiable randomness interface"],
        "baseline_failure_mode": "Baseline removes draw requirement entirely, making every caller instantly win.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TimestampLottery {
    address public winner;
    bytes32 public secretCommitment;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function setCommitment(bytes32 _commitment) external {
        require(msg.sender == owner, "Unauthorized");
        secretCommitment = _commitment;
    }

    function draw(string calldata revealSecret) external {
        require(keccak256(abi.encodePacked(revealSecret)) == secretCommitment, "Invalid reveal");
        winner = msg.sender;
    }
}"""
    },
    {
        "case_id": "case_14",
        "title": "Governance Voting Power Double-Spend",
        "category": "Governance",
        "difficulty": "Difficult",
        "vulnerability_type": "VOTING_DOUBLE_SPEND",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract GovernanceToken {
    mapping(address => uint256) public balances;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    mapping(uint256 => uint256) public proposalVotes;

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balances[msg.sender] >= amount, "Low balance");
        balances[msg.sender] -= amount;
        balances[to] += amount;
        return true;
    }

    function vote(uint256 proposalId) external {
        require(!hasVoted[proposalId][msg.sender], "Already voted");
        uint256 weight = balances[msg.sender];
        require(weight > 0, "No voting weight");

        hasVoted[proposalId][msg.sender] = true;
        proposalVotes[proposalId] += weight;
    }
}""",
        "vulnerability_description": "vote() reads live balances without snapshot/checkpoints. Attacker can vote with balance, transfer tokens to secondary wallet in same block, and vote again, multiplying voting power arbitrarily.",
        "exploit_poc": """Attacker holds 1,000 tokens. Calls vote(1), transfers 1,000 tokens to wallet 2, wallet 2 calls vote(1), multiplying votes 100x across Sybil wallets.""",
        "invariants": [
            "Voting power bounded by snapshot checkpoint balance at proposal creation block",
            "Single vote weight per token unit"
        ],
        "regression_tests": [
            {"name": "Standard Vote", "description": "Voter casts valid vote", "function_called": "vote", "caller": "0xUser1", "args": {"proposalId": 1}, "expected_success": True}
        ],
        "constraints": ["Track checkpoint / snapshot block or lock voting tokens during active voting period"],
        "baseline_failure_mode": "Baseline introduces mapping syntax errors or fails to lock voting balances.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract GovernanceToken {
    mapping(address => uint256) public balances;
    mapping(address => uint256) public lockedUntilProposal;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    mapping(uint256 => uint256) public proposalVotes;

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balances[msg.sender] >= amount, "Low balance");
        require(block.number > lockedUntilProposal[msg.sender], "Tokens locked in active vote");
        balances[msg.sender] -= amount;
        balances[to] += amount;
        return true;
    }

    function vote(uint256 proposalId, uint256 proposalEndBlock) external {
        require(!hasVoted[proposalId][msg.sender], "Already voted");
        uint256 weight = balances[msg.sender];
        require(weight > 0, "No voting weight");

        hasVoted[proposalId][msg.sender] = true;
        if (proposalEndBlock > lockedUntilProposal[msg.sender]) {
            lockedUntilProposal[msg.sender] = proposalEndBlock;
        }
        proposalVotes[proposalId] += weight;
    }
}"""
    },
    {
        "case_id": "case_15",
        "title": "Missing Slippage & Deadline Protection on AMM Swap",
        "category": "DEX / MEV",
        "difficulty": "Normal",
        "vulnerability_type": "SLIPPAGE_MISSING",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

contract AutoSwapper {
    IUniswapV2Router public router;

    constructor(address _router) {
        router = IUniswapV2Router(_router);
    }

    function swap(address tokenIn, address tokenOut, uint256 amountIn) external {
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;

        // Missing amountOutMin (0) and block.timestamp deadline allows sandwich attacks
        router.swapExactTokensForTokens(
            amountIn,
            0,
            path,
            msg.sender,
            block.timestamp + 1000
        );
    }
}""",
        "vulnerability_description": "amountOutMin is set to 0, allowing MEV sandwich bots to front-run the swap with large buys, push the price up, and back-run it to extract all user swap value.",
        "exploit_poc": """MEV searcher detects mempool swap, sandwiches transaction, returning near-zero tokens to victim.""",
        "invariants": [
            "Enforce minAmountOut parameter > 0 specified by caller",
            "Enforce caller-specified deadline"
        ],
        "regression_tests": [
            {"name": "Execute Swap with Slippage", "description": "Execute protected token swap", "function_called": "swap", "caller": "0xUser1", "args": {"amountIn": 100}, "expected_success": True}
        ],
        "constraints": ["Include minAmountOut and deadline parameters in swap() signature"],
        "baseline_failure_mode": "Baseline hardcodes fixed 1 wei slippage instead of caller input.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

contract AutoSwapper {
    IUniswapV2Router public router;

    constructor(address _router) {
        router = IUniswapV2Router(_router);
    }

    function swap(address tokenIn, address tokenOut, uint256 amountIn, uint256 minAmountOut, uint256 deadline) external {
        require(deadline >= block.timestamp, "Expired deadline");
        require(minAmountOut > 0, "Slippage protection required");
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;

        router.swapExactTokensForTokens(
            amountIn,
            minAmountOut,
            path,
            msg.sender,
            deadline
        );
    }
}"""
    },
    {
        "case_id": "case_16",
        "title": "Adversarial Multi-State Order Invariant Violation",
        "category": "Complex Multi-Hop",
        "difficulty": "Adversarial",
        "vulnerability_type": "REENTRANCY",
        "vulnerable_code": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MultiStateVault {
    mapping(address => uint256) public balances;
    mapping(address => uint256) public debt;
    uint256 public totalVaultCollateral;
    bool private locked;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
        totalVaultCollateral += msg.value;
    }

    function borrow(uint256 amount) external {
        require(balances[msg.sender] >= amount * 2, "Undercollateralized");
        debt[msg.sender] += amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Borrow payout failed");
    }

    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        require(balances[msg.sender] - amount >= debt[msg.sender] * 2, "Remaining collateral too low");

        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw payout failed");

        balances[msg.sender] -= amount;
        totalVaultCollateral -= amount;
    }
}""",
        "vulnerability_description": "Complex multi-state reentrancy: withdraw() sends ether before updating both balances[msg.sender] and totalVaultCollateral, allowing attacker to call borrow() during withdraw callback while balance is still considered un-withdrawn.",
        "exploit_poc": """Attacker deposits collateral, calls withdraw(), in fallback calls borrow() which checks un-reduced balances, doubling leverage and draining vault balance.""",
        "invariants": [
            "Solvency: totalVaultCollateral >= sum(balances)",
            "Collateralization ratio: balances[msg.sender] >= debt[msg.sender] * 2 at all execution boundaries",
            "No reentrant state bypass"
        ],
        "regression_tests": [
            {"name": "Deposit and Safe Withdraw", "description": "User deposits and performs normal withdrawal", "function_called": "withdraw", "caller": "0xUser1", "args": {"amount": 50}, "expected_success": True}
        ],
        "constraints": ["Apply nonReentrant modifier and CEI state updates before all external calls"],
        "baseline_failure_mode": "Baseline fixes withdraw() state update but misses cross-function reentrancy into borrow(), or updates totalVaultCollateral after transfer.",
        "gold_patch_reference": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MultiStateVault {
    mapping(address => uint256) public balances;
    mapping(address => uint256) public debt;
    uint256 public totalVaultCollateral;
    bool private _locked;

    modifier nonReentrant() {
        require(!_locked, "ReentrancyGuard: reentrant call");
        _locked = true;
        _;
        _locked = false;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
        totalVaultCollateral += msg.value;
    }

    function borrow(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount * 2, "Undercollateralized");
        debt[msg.sender] += amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Borrow payout failed");
    }

    function withdraw(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        require(balances[msg.sender] - amount >= debt[msg.sender] * 2, "Remaining collateral too low");

        balances[msg.sender] -= amount;
        totalVaultCollateral -= amount;

        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw payout failed");
    }
}"""
    }
]

def generate_benchmark():
    cases_dir = Path("/Users/kaizen/Desktop/litmus/benchmark/cases")
    gold_dir = Path("/Users/kaizen/Desktop/litmus/benchmark/gold")
    cases_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    gold_references = {}

    for c in CASES:
        case_id = c["case_id"]
        filename = f"{case_id}_{c['category'].lower().replace(' ', '_').replace('/', '_')}.json"
        case_path = cases_dir / filename
        
        with open(case_path, "w") as f:
            json.dump(c, f, indent=2)

        gold_references[case_id] = {
            "title": c["title"],
            "vulnerability_type": c["vulnerability_type"],
            "gold_patch": c["gold_patch_reference"],
            "invariants": c["invariants"]
        }

    with open(gold_dir / "reference_solutions.json", "w") as f:
        json.dump(gold_references, f, indent=2)

    print(f"Generated {len(CASES)} benchmark cases in {cases_dir}")
    print(f"Generated gold references in {gold_dir / 'reference_solutions.json'}")

if __name__ == "__main__":
    generate_benchmark()
