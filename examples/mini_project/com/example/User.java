package com.example;

/**
 * Demonstrates resolution of "Outer.Inner" dot-notation (rule 1b, 2 parts).
 * JASTG resolves Foo.Inner -> com.example.Foo$Inner.
 */
public class User {
    private Foo.Inner innerRef;
}
