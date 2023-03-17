ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

SRCDIR = src
MEMCACHED_SRC ?= memcached-1.5.21.tar.gz
MEMCACHED_MIRRORS ?= \
    https://memcached.org/files \
    https://packages.gramineproject.io/distfiles

MEMCACHED_SHA256 ?= e3d10c06db755b220f43d26d3b68d15ebf737a69c7663529b504ab047efe92f4
# LIBMEMCACHED_SHA256 ?= e22c0bb032fde08f53de9ffbc5a128233041d9f33b5de022c0978a2149885f82

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

.PHONY: all
all: memcached memcached.manifest memtier_benchmark/memtier_benchmark
ifeq ($(SGX),1)
all: memcached.manifest.sgx memcached.sig
endif

memcached.tar.gz:
	./download --output memcached.tar.gz --sha256 $(MEMCACHED_SHA256) \
		$(foreach mirror,$(MEMCACHED_MIRRORS),--url $(mirror)/$(MEMCACHED_SRC))

# libmemcached.tar.gz:
# 	./download --output libmemcached.tar.gz --sha256 $(LIBMEMCACHED_SHA256) \
# 	--url 'https://launchpad.net/libmemcached/1.0/1.0.18/+download/libmemcached-1.0.18.tar.gz'

# libmemcached/configure: libmemcached.tar.gz
# 	rm -rf libmemcached
# 	mkdir libmemcached
# 	tar -C libmemcached --strip-components=1 -xf libmemcached.tar.gz

# libmemcached/memaslap: libmemcached/configure
# 	cd libmemcached && ./configure --enable-memaslap --disable-sasl
# 	make -C libmemcached -j8

$(SRCDIR)/.MEMCACHED_DOWNLOADED: memcached.tar.gz
	rm -rf $(SRCDIR)
	mkdir $(SRCDIR)
	tar -C $(SRCDIR) --strip-components=1 -xf memcached.tar.gz
	sed -i 's/-Werror//g' $(SRCDIR)/configure
	cd $(SRCDIR) && patch -p1 < ../memcached_hash.patch
	touch $(SRCDIR)/.MEMCACHED_DOWNLOADED

$(SRCDIR)/memcached: $(SRCDIR)/.MEMCACHED_DOWNLOADED
	cd $(SRCDIR) && ./configure
	$(MAKE) -C $(SRCDIR)

memtier_benchmark/configure.ac:
	git clone https://github.com/RedisLabs/memtier_benchmark.git
	git -C memtier_benchmark checkout 29f51a82158d5c1002deab1cfb7ee32af96357fe

memtier_benchmark/memtier_benchmark: memtier_benchmark/configure.ac
	cd memtier_benchmark && autoreconf -ivf
	cd memtier_benchmark && ./configure
	cd memtier_benchmark && make -j8

memcached.manifest: memcached.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		$< > $@

# Make on Ubuntu <= 20.04 doesn't support "Rules with Grouped Targets" (`&:`),
# see the helloworld example for details on this workaround.
memcached.manifest.sgx memcached.sig: sgx_sign
	@:

.INTERMEDIATE: sgx_sign
sgx_sign: memcached.manifest memcached
	gramine-sgx-sign \
		--manifest $< \
		--output $<.sgx

# for simplicity, copy memcached executable into our root directory
memcached: $(SRCDIR)/memcached
	cp $< $@

.PHONY: start-native-server
start-native-server: all
	./memcached

ifeq ($(SGX),)
GRAMINE = gramine-direct
else
GRAMINE = gramine-sgx
endif

.PHONY: start-gramine-server
start-gramine-server: all
	$(GRAMINE) memcached

.PHONY: clean
clean:
	$(RM) *.sig *.manifest.sgx memcached.token *.manifest memcached .lck

.PHONY: distclean
distclean: clean
	$(RM) -r $(SRCDIR) memcached.tar.gz libmemcached/ libmemcached.tar.gz memtier_benchmark/
