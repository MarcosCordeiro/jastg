package com.other;

/**
 * Demonstrates resolution of fully-qualified "pkg.Outer.Inner" dot-notation
 * (rule 1b, 3+ parts).
 * JASTG resolves com.example.Foo.Inner -> com.example.Foo$Inner.
 */
public class User2 {
    private com.example.Foo.Inner qualifiedInnerRef;
}
