package com.example;

import com.other.Helper;
import static com.other.Helper.staticMethod;

/**
 * Example class demonstrating multiple dependency types captured by JASTG:
 *   - extends (Bar)
 *   - implements (Baz)
 *   - field types (Qux, Helper)
 *   - method parameter type (Qux)
 *   - method return type (Baz)
 *   - ClassCreator (new Bar())
 *   - LocalVariableDeclaration (Bar local)
 *   - Cast ((Qux) algo)
 *   - inner class (Foo.Inner)
 *   - multilevel inner class (Foo.Inner.Deep)
 */
public class Foo extends Bar implements Baz {
    private Qux atributo;
    private Helper helper;

    public Baz metodo(Qux param) {
        Bar local = new Bar();
        Qux outro = (Qux) algo;
        return null;
    }

    public class Inner {
        private Bar ref;

        public void doSomething() {
            new Qux();
        }

        public class Deep {
            private Qux deepRef;
        }
    }
}
