package com.other;

import com.example.Foo;

/**
 * Cross-package class that imports Foo explicitly.
 * JASTG resolves it via explicit import (rule 2).
 */
public class Helper {
    private Foo foo;

    public static void staticMethod() {
        // static method – its import is ignored by JASTG (by design)
    }
}
