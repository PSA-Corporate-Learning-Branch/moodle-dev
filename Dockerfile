FROM php:8.1-apache

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    unzip \
    libpng-dev \
    libjpeg-dev \
    libfreetype6-dev \
    libxml2-dev \
    libzip-dev \
    libicu-dev \
    libldap2-dev \
    libonig-dev \
    libcurl4-openssl-dev \
    libxslt-dev \
    libpq-dev \
    zlib1g-dev \
    default-mysql-client \
    curl \
    ca-certificates \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create dev user for Claude Code usage
RUN useradd -m -s /bin/bash -G www-data dev \
    && echo "dev ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Configure and install PHP extensions required by Moodle
RUN docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j$(nproc) \
    gd \
    mysqli \
    pdo \
    pdo_mysql \
    xml \
    zip \
    intl \
    ldap \
    soap \
    mbstring \
    curl \
    exif \
    opcache \
    xsl

# Enable Apache modules
RUN a2enmod rewrite headers

# Configure PHP for Moodle
RUN { \
    echo 'max_execution_time = 300'; \
    echo 'memory_limit = 256M'; \
    echo 'post_max_size = 100M'; \
    echo 'upload_max_filesize = 100M'; \
    echo 'max_input_vars = 5000'; \
    echo 'max_input_time = 600'; \
} > /usr/local/etc/php/conf.d/moodle.ini

# Configure OPcache for Moodle
RUN { \
    echo 'opcache.enable=1'; \
    echo 'opcache.memory_consumption=128'; \
    echo 'opcache.max_accelerated_files=10000'; \
    echo 'opcache.revalidate_freq=60'; \
    echo 'opcache.use_cwd=1'; \
    echo 'opcache.validate_timestamps=1'; \
    echo 'opcache.save_comments=1'; \
} > /usr/local/etc/php/conf.d/opcache.ini

# Set working directory
WORKDIR /var/www/html

# Download Moodle 4.5 (latest stable)
RUN git clone --depth 1 --branch MOODLE_405_STABLE https://github.com/moodle/moodle.git . \
    && rm -rf .git

# Plugin and theme directories will be mounted as volumes for development

# Create moodledata directory
RUN mkdir -p /var/www/moodledata \
    && chown -R www-data:www-data /var/www/moodledata \
    && chmod 755 /var/www/moodledata

# Set ownership for Moodle directory
RUN chown -R www-data:www-data /var/www/html

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy config template
COPY config.php.template /var/www/html/config.php.template

EXPOSE 80

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["apache2-foreground"]
