.PHONY: package test clean

package: clean
	mkdir -p build
	cp lambda_function.py config.py allowlist.py build/
	cd build && zip -r ../deployment.zip .
	@echo "Created deployment.zip"

test:
	python -m pytest tests/ -v

clean:
	rm -rf build/ deployment.zip
