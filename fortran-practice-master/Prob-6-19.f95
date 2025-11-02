program sets
    implicit none
    integer, parameter :: SIZE = 100
    integer, dimension(SIZE) :: a1, a2, a_u, a_i 
    integer :: nvals1 = 0, nvals2 = 0, nvals_u = 0, nvals_i = 0
    integer :: i, j, iostat
    logical :: in_set, match
    real :: temp 
    character(len=20) :: filename 

    ! Get the name of the file containing the first set
    write (*, '(1x,A)') 'Enter the file name with the first set: '
    read (*, '(A20)') filename 

    ! Open input data file. Status is OLD because the input data must
    ! already exist.
    open (unit=10, file=filename, status='old', iostat=iostat)

    if (iostat == 0) then ! Open successful 

        ! Read values from the file into the first array
        do
            read (10, *, iostat=iostat) temp 
            if (iostat /= 0) exit 
            nvals1 = nvals1 + 1 
            a1(nvals1) = int(temp)
        end do 

        close(10) 
    end if

    ! Get the name of the file containing the second set
    write (*, '(1x,A)') 'Enter the file name with the second set: '
    read (*, '(A20)') filename 

    ! Open input data file. Status is OLD because the input data must 
    ! already exist.
    open (unit=20, file=filename, status='old', iostat=iostat)

    if (iostat == 0) then ! Open successful

        ! Read values from the file into the second array
        do 
            read (20, *, iostat=iostat) temp
            if (iostat /= 0) exit 
        
            nvals2 = nvals2 + 1 
            a2(nvals2) = int(temp)
        end do 
        close(20)
    end if 

    ! Compute the union of the two sets 
    ! First, copy all values from the first set into the union set
    do i = 1, nvals1
        in_set = .false.

        do j = 1, nvals_u
            if (a1(i) == a_u(j)) then 
                in_set = .true. 
                exit 
            end if 
        end do 

        if (.not. in_set) then 
            nvals_u = nvals_u + 1 
            a_u(nvals_u) = a1(i)
        end if

    end do 

    ! Next, add values from the second set that are not already in the union set
    do i = 1, nvals2 
        in_set = .false.

        do j = 1, nvals_u 
            if (a2(i) == a_u(j)) then 
                in_set = .true.
                exit 
            end if 
        end do 

        if (.not. in_set) then 
            nvals_u = nvals_u + 1 
            a_u(nvals_u) = a2(i) 
        end if 
    end do 

    ! Compute the intersection of the two sets 
    do i = 1, nvals1 
        match = .false.

        do j = 1, nvals2 
            if (a1(i) == a2(j)) then 
                match = .true.
                exit 
            end if 
        end do 

        if (match) then 
            in_set = .false. 

            do j = 1, nvals_i 
                if (a1(i) == a_i(j)) then 
                    in_set = .true.
                    exit 
                end if 
            end do 

            if (.not. in_set) then 
                nvals_i = nvals_i + 1 
                a_i(nvals_i) = a1(i) 
            end if 

        end if 
    end do

    ! Print the first set
    write (*, '(1x,A, 20I5)') 'Set 1        : ', (a1(i), i = 1, nvals1)

    ! Print the second set
    write (*, '(1x,A, 20I5)') 'Set 2        : ', (a2(i), i = 1, nvals2)

    ! Print the union set 
    write (*, '(1x,A, 20I5)') 'Union        : ', (a_u(i), i = 1, nvals_u)
    
    ! Print the intersection set 
    write (*, '(1x,A, 20I5)') 'Intersection : ', (a_i(i), i = 1, nvals_i)

end program sets