# Storekit environments

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## StoreKit request success does not prove update delivery

Capture the measured Mac state where local products/purchases worked but transaction updates were routed to Sandbox and not delivered to XcodeTest. Use an independent updates listener to distinguish service delivery from model handling. Keep product-price availability separate from verified entitlement access, and explicit restore separate from launch.

[Pagepour measurements/storekit-lifetime/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/storekit-lifetime/record.md#mac-transaction-updates-on-2026-10-08) and [Pagepour doc/purchase-policy.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/purchase-policy.md). The environment-switch behavior is a recorded host-specific observation, not a general StoreKit contract or a reason to weaken shipping entitlement verification.
