<!-- Real output of: qa-copilot run --model qwen2.5:1.5b --format md
     Story: "As a customer I want to pay for my online order using a credit card or a gift card"
     Generated fully offline by a 1.5B-parameter local model; excerpt, content unedited. -->

# QA Report

## Requirement analysis

The requirement states that customers can pay for online orders using credit cards or gift cards. However, it does not specify how these payments are processed or what happens if a customer chooses one method over another.

**Readiness:** 82/100 - Ready for test design

### Gaps

- **GAP-001** [High] Payment method selection - The requirement does not specify how customers can choose between credit card and gift card payment methods.

### Ambiguities

- **AMB-001** [Medium] Payment method selection - The requirement is unclear about whether gift cards can be used for partial payments or if they are always for the full amount.

### Risks

| Risk | L | I | Score | Level | Mitigation |
|---|---|---|---|---|---|
| If gift cards are not accepted for partial payments, customers may be unable to complete their orders. | 4 | 3 | 12 | High | Implement a system that allows gift cards to be used for partial payments or provide a clear message to customers that gift cards cannot be used for partial amounts. |

### Acceptance criteria

- AC-1: Provide a clear and intuitive method for customers to select their preferred payment method.

### Clarification questions

1. **Q-001** (High) How should customers be informed about the payment method selection process?

## Coverage

- Total test cases: **17**
- By category: {'Positive': 4, 'Negative': 4, 'Boundary': 3, 'Edge Case': 3, 'Regression': 3}
- Automatable: 100%
- Acceptance-criteria coverage: 100%
- Uncovered items: AMB-001

## Test cases

### TC-001 - Customer selects credit card as payment method

*Positive | High | Payment Method Selection*

**Preconditions:** Customer is logged in and has a valid credit card on file
**Test data:** credit_card_number=1234567890123456, credit_card_expiry=12/25, credit_card_cvv=123

**Steps:**
1. Navigate to checkout
2. Select 'Credit Card'
3. Enter credit card details

**Expected:** Credit card payment method selected successfully

**Traces to:** AC-1, GAP-001

### TC-002 - Customer selects gift card as payment method

*Positive | High | Payment Method Selection*

**Preconditions:** Customer is logged in and has a valid gift card on file
**Test data:** gift_card_number=1234567890123456, gift_card_expiry=12/25, gift_card_cvv=123

**Steps:**
1. Navigate to checkout
2. Select 'Gift Card'
3. Enter gift card details

**Expected:** Gift card payment method selected successfully

**Traces to:** AC-1, GAP-001

### TC-005 - Customer tries to select gift card as payment method without a gift card on file

*Negative | Low | Payment Method Selection*

**Preconditions:** Customer is logged in but has no gift card on file

**Steps:**
1. Navigate to checkout
2. Select 'Gift Card'
3. Enter gift card details

**Expected:** Gift card payment method selection fails with error

**Traces to:** GAP-001

### TC-009 - User selects a payment method that is not available

*Boundary | Low | Payment Method Selection*

**Preconditions:** Customer is logged in and has a valid credit card on file
**Test data:** Credit card number: 1234 5678 9012 3456, Expiration: 12/25, CVV: 123

**Steps:**
1. Navigate to checkout
2. Select 'PayPal' from payment methods
3. Proceed to payment page

**Expected:** Payment method not available error

**Traces to:** GAP-001

*(Excerpt: 4 of the 17 generated cases shown. Run the tool to see the full report.)*
